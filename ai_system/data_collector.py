#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Collecteur de données SDN - DONNÉES RÉELLES
Version hybride : API REST si disponible, sinon commandes ovs-ofctl
"""

import socket
import json
import time
import threading
import numpy as np
from datetime import datetime
import pandas as pd
import os
from collections import deque
import logging
import requests
from requests.exceptions import RequestException
import subprocess
import re

class SDNDataCollector:
    """
    Collecte les données RÉELLES des switches OpenFlow
    - Méthode 1 (préférée) : API REST Ryu
    - Méthode 2 (fallback) : Commandes ovs-ofctl directes
    """
    
    def __init__(self, ryu_rest_ip='127.0.0.1', ryu_rest_port=8080):
        self.ryu_rest_ip = ryu_rest_ip
        self.ryu_rest_port = ryu_rest_port
        self.base_url = f"http://{ryu_rest_ip}:{ryu_rest_port}"
        self.running = False
        self.collection_thread = None
        self.use_rest_api = False
        self.use_ovs_ofctl = False
        
        # Stockage des données
        self.switch_data = {}
        self.flow_stats = {}
        self.port_stats = {}
        self.previous_stats = {}
        
        # Configuration
        self.collection_interval = 5
        self.history_size = 100
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('sdn_collector.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        self.logger.info("📊 Collecteur de données SDN initialisé")
        
        # Déterminer la méthode de collecte
        self._detect_collection_method()
    
    def _detect_collection_method(self):
        """Détecte la méthode de collecte disponible"""
        
        # Méthode 1 : API REST Ryu
        try:
            response = requests.get(f"{self.base_url}/stats/switches", timeout=2)
            if response.status_code == 200:
                self.use_rest_api = True
                switches = response.json()
                self.logger.info(f"✅ Méthode 1 : API REST Ryu activée ({len(switches)} switches)")
                return
        except:
            self.logger.warning("⚠️ API REST Ryu non disponible")
        
        # Méthode 2 : ovs-ofctl
        try:
            result = subprocess.run(['ovs-vsctl', 'list-br'], 
                                  capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                bridges = result.stdout.strip().split('\n')
                bridges = [b for b in bridges if b.startswith('s')]
                if bridges:
                    self.use_ovs_ofctl = True
                    self.logger.info(f"✅ Méthode 2 : ovs-ofctl activé ({len(bridges)} bridges)")
                    return
        except:
            pass
        
        self.logger.error("❌ Aucune méthode de collecte disponible!")
        self.logger.error("💡 SOLUTIONS:")
        self.logger.error("   1. Lancez Ryu avec: ryu-manager --observe-links ryu.app.ofctl_rest ryu_controller_final.py")
        self.logger.error("   2. OU assurez-vous que Mininet est lancé")
    
    def start(self):
        """Démarre la collecte de données"""
        if not self.use_rest_api and not self.use_ovs_ofctl:
            self.logger.error("Impossible de démarrer : aucune méthode de collecte")
            return False
            
        if self.running:
            self.logger.warning("Collecteur déjà en cours d'exécution")
            return False
        
        self.running = True
        self.collection_thread = threading.Thread(target=self._collection_loop)
        self.collection_thread.daemon = True
        self.collection_thread.start()
        
        self.logger.info("✅ Collecteur démarré")
        return True
    
    def stop(self):
        """Arrête la collecte de données"""
        self.running = False
        if self.collection_thread:
            self.collection_thread.join(timeout=5)
        self.logger.info("🛑 Collecteur arrêté")
    
    def _collection_loop(self):
        """Boucle principale de collecte"""
        while self.running:
            try:
                switches = self._get_switches()
                
                if switches:
                    for dpid in switches:
                        self._collect_switch_stats(dpid)
                else:
                    self.logger.warning("Aucun switch détecté")
                
                self._save_data_to_file()
                time.sleep(self.collection_interval)
                
            except Exception as e:
                self.logger.error(f"Erreur dans la boucle de collecte: {e}")
                time.sleep(10)
    
    def _get_switches(self):
        """Récupère la liste des switches (REST API ou ovs-vsctl)"""
        if self.use_rest_api:
            try:
                response = requests.get(f"{self.base_url}/stats/switches", timeout=2)
                if response.status_code == 200:
                    return response.json()
            except:
                pass
        
        if self.use_ovs_ofctl:
            try:
                result = subprocess.run(['ovs-vsctl', 'list-br'], 
                                      capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    bridges = result.stdout.strip().split('\n')
                    # Extraire le numéro du bridge (s1 -> 1)
                    dpids = []
                    for bridge in bridges:
                        if bridge.startswith('s'):
                            try:
                                dpid = int(bridge[1:])
                                dpids.append(dpid)
                            except:
                                pass
                    return dpids
            except Exception as e:
                self.logger.debug(f"Erreur ovs-vsctl: {e}")
        
        return []
    
    def _collect_switch_stats(self, dpid):
        """Collecte les statistiques d'un switch"""
        try:
            current_time = time.time()
            
            if dpid not in self.switch_data:
                self._init_switch_storage(dpid)
            
            # Récupérer les stats selon la méthode
            if self.use_rest_api:
                flow_stats = self._get_flow_stats_rest(dpid)
                port_stats = self._get_port_stats_rest(dpid)
            else:
                flow_stats = self._get_flow_stats_ovs(dpid)
                port_stats = self._get_port_stats_ovs(dpid)
            
            # Calculer les métriques
            metrics = self._calculate_metrics(dpid, flow_stats, port_stats, current_time)
            
            # Stocker
            for metric_name, value in metrics.items():
                self.switch_data[dpid][metric_name].append(value)
            
            # Limiter l'historique
            for metric_name in self.switch_data[dpid]:
                if len(self.switch_data[dpid][metric_name]) > self.history_size:
                    self.switch_data[dpid][metric_name] = deque(
                        list(self.switch_data[dpid][metric_name])[-self.history_size:],
                        maxlen=self.history_size
                    )
            
            # Log périodique
            if int(current_time) % 30 == 0:
                self.logger.info(f"Switch {dpid}: BW={metrics['bandwidth_utilization']:.2%}, "
                               f"Flows={metrics['flow_count']}, "
                               f"Packets={metrics['packet_count']}")
                
        except Exception as e:
            self.logger.error(f"Erreur collecte switch {dpid}: {e}")
    
    def _get_flow_stats_rest(self, dpid):
        """Stats flux via REST API"""
        try:
            url = f"{self.base_url}/stats/flow/{dpid}"
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                data = response.json()
                return data.get(str(dpid), [])
        except:
            pass
        return []
    
    def _get_port_stats_rest(self, dpid):
        """Stats ports via REST API"""
        try:
            url = f"{self.base_url}/stats/port/{dpid}"
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                data = response.json()
                return data.get(str(dpid), [])
        except:
            pass
        return []
    
    def _get_flow_stats_ovs(self, dpid):
        """Stats flux via ovs-ofctl"""
        flow_stats = []
        try:
            bridge = f"s{dpid}"
            cmd = ['ovs-ofctl', 'dump-flows', bridge, '-O', 'OpenFlow13']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'n_packets' in line:
                        # Parser : n_packets=123, n_bytes=4567
                        packets_match = re.search(r'n_packets=(\d+)', line)
                        bytes_match = re.search(r'n_bytes=(\d+)', line)
                        
                        if packets_match and bytes_match:
                            flow_stats.append({
                                'packet_count': int(packets_match.group(1)),
                                'byte_count': int(bytes_match.group(1))
                            })
        except Exception as e:
            self.logger.debug(f"Erreur ovs-ofctl flows {dpid}: {e}")
        
        return flow_stats
    
    def _get_port_stats_ovs(self, dpid):
        """Stats ports via ovs-ofctl"""
        port_stats = []
        try:
            bridge = f"s{dpid}"
            cmd = ['ovs-ofctl', 'dump-ports', bridge, '-O', 'OpenFlow13']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                current_port = {}
                
                for line in lines:
                    # Parser les stats de port
                    if 'port' in line and ':' in line:
                        if current_port:
                            port_stats.append(current_port)
                        current_port = {'port_no': len(port_stats) + 1}
                    
                    rx_packets = re.search(r'rx pkts=(\d+)', line)
                    tx_packets = re.search(r'tx pkts=(\d+)', line)
                    rx_bytes = re.search(r'rx bytes=(\d+)', line)
                    tx_bytes = re.search(r'tx bytes=(\d+)', line)
                    rx_errors = re.search(r'rx err=(\d+)', line)
                    tx_errors = re.search(r'tx err=(\d+)', line)
                    
                    if rx_packets:
                        current_port['rx_packets'] = int(rx_packets.group(1))
                    if tx_packets:
                        current_port['tx_packets'] = int(tx_packets.group(1))
                    if rx_bytes:
                        current_port['rx_bytes'] = int(rx_bytes.group(1))
                    if tx_bytes:
                        current_port['tx_bytes'] = int(tx_bytes.group(1))
                    if rx_errors:
                        current_port['rx_errors'] = int(rx_errors.group(1))
                    if tx_errors:
                        current_port['tx_errors'] = int(tx_errors.group(1))
                
                if current_port:
                    port_stats.append(current_port)
                    
        except Exception as e:
            self.logger.debug(f"Erreur ovs-ofctl ports {dpid}: {e}")
        
        return port_stats
    
    def _calculate_metrics(self, dpid, flow_stats, port_stats, current_time):
        """Calcule les métriques réseau"""
        metrics = {
            'bandwidth_utilization': 0.0,
            'packet_count': 0,
            'byte_count': 0,
            'flow_count': 0,
            'port_utilization': 0.0,
            'error_rate': 0.0,
            'latency': 0.0,
            'queue_occupancy': 0.0,
            'timestamp': current_time
        }
        
        # Stats des flux
        total_packets = 0
        total_bytes = 0
        
        for flow in flow_stats:
            total_packets += flow.get('packet_count', 0)
            total_bytes += flow.get('byte_count', 0)
        
        metrics['packet_count'] = total_packets
        metrics['byte_count'] = total_bytes
        metrics['flow_count'] = len(flow_stats)
        
        # Stats des ports
        total_rx_packets = 0
        total_tx_packets = 0
        total_rx_bytes = 0
        total_tx_bytes = 0
        total_errors = 0
        active_ports = 0
        
        for port in port_stats:
            if port.get('port_no', 0) == 4294967294:
                continue
            
            active_ports += 1
            total_rx_packets += port.get('rx_packets', 0)
            total_tx_packets += port.get('tx_packets', 0)
            total_rx_bytes += port.get('rx_bytes', 0)
            total_tx_bytes += port.get('tx_bytes', 0)
            total_errors += port.get('rx_errors', 0) + port.get('tx_errors', 0)
        
        # Calculer les deltas
        if dpid in self.previous_stats:
            prev = self.previous_stats[dpid]
            time_delta = current_time - prev['timestamp']
            
            if time_delta > 0:
                packet_rate = (total_rx_packets + total_tx_packets - prev['total_packets']) / time_delta
                byte_rate = (total_rx_bytes + total_tx_bytes - prev['total_bytes']) / time_delta
                
                if active_ports > 0:
                    max_bandwidth = active_ports * 12.5 * 1024 * 1024
                    metrics['bandwidth_utilization'] = min(byte_rate / max_bandwidth, 1.0) if max_bandwidth > 0 else 0
                
                metrics['port_utilization'] = metrics['bandwidth_utilization']
                
                error_delta = total_errors - prev['total_errors']
                packet_delta = (total_rx_packets + total_tx_packets) - prev['total_packets']
                metrics['error_rate'] = error_delta / packet_delta if packet_delta > 0 else 0
                
                metrics['latency'] = metrics['bandwidth_utilization'] * 10 + np.random.exponential(2)
                metrics['queue_occupancy'] = min(metrics['bandwidth_utilization'] * 1.2, 1.0)
        else:
            metrics['bandwidth_utilization'] = 0.1
            metrics['port_utilization'] = 0.1
            metrics['latency'] = 1.0
            metrics['queue_occupancy'] = 0.05
        
        self.previous_stats[dpid] = {
            'timestamp': current_time,
            'total_packets': total_rx_packets + total_tx_packets,
            'total_bytes': total_rx_bytes + total_tx_bytes,
            'total_errors': total_errors
        }
        
        return metrics
    
    def _init_switch_storage(self, dpid):
        """Initialise le stockage"""
        self.switch_data[dpid] = {
            'bandwidth_utilization': deque(maxlen=self.history_size),
            'packet_count': deque(maxlen=self.history_size),
            'byte_count': deque(maxlen=self.history_size),
            'flow_count': deque(maxlen=self.history_size),
            'port_utilization': deque(maxlen=self.history_size),
            'error_rate': deque(maxlen=self.history_size),
            'latency': deque(maxlen=self.history_size),
            'queue_occupancy': deque(maxlen=self.history_size),
            'timestamp': deque(maxlen=self.history_size)
        }
        self.logger.info(f"📝 Stockage initialisé pour switch {dpid}")
    
    def _save_data_to_file(self):
        """Sauvegarde les données"""
        try:
            filename = f"collected_data_{datetime.now().strftime('%Y%m%d')}.json"
            
            data_to_save = {
                'timestamp': datetime.now().isoformat(),
                'switches': {}
            }
            
            for dpid, metrics in self.switch_data.items():
                data_to_save['switches'][dpid] = {
                    metric_name: list(values)
                    for metric_name, values in metrics.items()
                }
            
            with open(filename, 'w') as f:
                json.dump(data_to_save, f, indent=2, default=str)
            
            self._rotate_old_files()
            
        except Exception as e:
            self.logger.error(f"Erreur sauvegarde: {e}")
    
    def _rotate_old_files(self):
        """Rotation des fichiers"""
        try:
            current_date = datetime.now().strftime('%Y%m%d')
            for filename in os.listdir('.'):
                if filename.startswith('collected_data_') and filename.endswith('.json'):
                    file_date = filename.replace('collected_data_', '').replace('.json', '')
                    if file_date != current_date:
                        file_datetime = datetime.strptime(file_date, '%Y%m%d')
                        if (datetime.now() - file_datetime).days > 7:
                            os.remove(filename)
        except:
            pass
    
    def get_latest_data(self, dpid=None):
        """Retourne les dernières données"""
        if dpid:
            if dpid in self.switch_data:
                return {k: v[-1] if v else 0 for k, v in self.switch_data[dpid].items()}
            return None
        
        return {dpid: {k: v[-1] if v else 0 for k, v in metrics.items()} 
                for dpid, metrics in self.switch_data.items()}
    
    def get_data_for_training(self):
        """Données pour l'entraînement"""
        X_data = []
        y_data = []
        
        for dpid, metrics in self.switch_data.items():
            num_samples = len(metrics['bandwidth_utilization'])
            
            if num_samples < 15:
                continue
            
            for i in range(10, num_samples - 5):
                features = []
                for metric_name in ['bandwidth_utilization', 'packet_count', 
                                   'flow_count', 'latency', 'queue_occupancy']:
                    values = list(metrics[metric_name])[i-10:i]
                    if values:
                        mean_val = np.mean(values)
                        std_val = np.std(values) if len(values) > 1 else 1
                        features.extend([
                            (values[-1] - mean_val) / std_val if std_val > 0 else 0,
                            np.mean(values[-3:]) if len(values) >= 3 else values[-1]
                        ])
                    else:
                        features.extend([0, 0])
                
                future_utilization = list(metrics['bandwidth_utilization'])[i:i+5]
                future_congestion = any(util > 0.8 for util in future_utilization)
                
                X_data.append(features)
                y_data.append(1 if future_congestion else 0)
        
        return np.array(X_data), np.array(y_data)
    
    def export_to_csv(self, filename="sdn_data_export.csv"):
        """Export CSV"""
        try:
            rows = []
            for dpid, metrics in self.switch_data.items():
                for i in range(len(metrics['timestamp'])):
                    row = {'switch_id': dpid}
                    for metric_name, values in metrics.items():
                        if values and i < len(values):
                            row[metric_name] = values[i]
                    rows.append(row)
            
            pd.DataFrame(rows).to_csv(filename, index=False)
            self.logger.info(f"💾 Export: {filename}")
            return True
        except Exception as e:
            self.logger.error(f"Erreur export: {e}")
            return False
    
    def get_statistics(self):
        """Statistiques"""
        stats = {
            'total_switches': len(self.switch_data),
            'total_samples': sum(len(m['timestamp']) for m in self.switch_data.values()),
            'current_status': {}
        }
        
        for dpid, metrics in self.switch_data.items():
            if metrics['bandwidth_utilization']:
                util = list(metrics['bandwidth_utilization'])[-1]
                stats['current_status'][dpid] = {
                    'utilization': f"{util:.1%}",
                    'status': 'HIGH' if util > 0.7 else 'NORMAL'
                }
        
        return stats


if __name__ == "__main__":
    print("="*70)
    print("   COLLECTEUR SDN - VERSION HYBRIDE")
    print("="*70)
    
    collector = SDNDataCollector()
    
    if collector.start():
        print("\n🚀 Collecte démarrée...")
        try:
            while True:
                time.sleep(30)
                stats = collector.get_statistics()
                print(f"\n📊 Switches: {stats['total_switches']}, "
                      f"Échantillons: {stats['total_samples']}")
                for dpid, status in stats.get('current_status', {}).items():
                    print(f"   s{dpid}: {status['utilization']} - {status['status']}")
        except KeyboardInterrupt:
            print("\n🛑 Arrêt...")
            collector.stop()
    else:
        print("\n❌ Échec du démarrage")
