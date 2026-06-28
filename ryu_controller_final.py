#!/usr/bin/python
# -*- coding: utf-8 -*-
# Nom du fichier: ryu_controller_final.py

"""
Contrôleur SDN L2 Learning Switch
Version finale corrigée avec filtrage multicast et logs détaillés
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types


class L2SwitchController(app_manager.RyuApp):
    """Contrôleur simple avec apprentissage des adresses MAC"""
    
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(L2SwitchController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.logger.info("="*80)
        self.logger.info("   CONTRÔLEUR SDN L2 LEARNING SWITCH DÉMARRÉ")
        self.logger.info("="*80)
        self.logger.info("En attente de connexion des switches...")
        self.logger.info("")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """
        Gère la connexion initiale d'un switch.
        Installe les règles par défaut.
        """
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        self.logger.info("="*80)
        self.logger.info("✅ SWITCH CONNECTÉ: s%d (DPID=%016x)", dpid, dpid)
        self.logger.info("="*80)

        # RÈGLE 1: Bloquer le multicast IPv6 (33:33:xx:xx:xx:xx)
        # Ces paquets causent des tempêtes de broadcast
        match = parser.OFPMatch(eth_dst=('33:33:00:00:00:00', 'ff:ff:00:00:00:00'))
        actions = []  # Aucune action = DROP
        self.add_flow(datapath, 100, match, actions)
        self.logger.info("   [s%d] Règle 1: BLOQUER multicast IPv6 (33:33:xx:xx:xx:xx)", dpid)

        # RÈGLE 2: Bloquer broadcast excessif (ff:ff:ff:ff:ff:ff)
        match = parser.OFPMatch(eth_dst='ff:ff:ff:ff:ff:ff')
        actions = []  # DROP
        self.add_flow(datapath, 99, match, actions)
        self.logger.info("   [s%d] Règle 2: BLOQUER broadcast (ff:ff:ff:ff:ff:ff)", dpid)

        # RÈGLE 3: Bloquer multicast IPv4 (01:00:5e:xx:xx:xx)
        match = parser.OFPMatch(eth_dst=('01:00:5e:00:00:00', 'ff:ff:ff:00:00:00'))
        actions = []  # DROP
        self.add_flow(datapath, 98, match, actions)
        self.logger.info("   [s%d] Règle 3: BLOQUER multicast IPv4 (01:00:5e:xx:xx:xx)", dpid)

        # RÈGLE 4: Table-miss (priorité la plus basse)
        # Tous les paquets non matchés sont envoyés au contrôleur
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        self.logger.info("   [s%d] Règle 4: Table-miss → Envoyer au contrôleur", dpid)
        self.logger.info("="*80)
        self.logger.info("")

    def add_flow(self, datapath, priority, match, actions, 
                 buffer_id=None, idle_timeout=0, hard_timeout=0):
        """
        Ajoute une règle de flux dans la table OpenFlow d'un switch.
        
        Args:
            datapath: Le switch cible
            priority: Priorité de la règle (plus élevé = prioritaire)
            match: Critères de correspondance
            actions: Actions à effectuer
            buffer_id: ID du buffer (optionnel)
            idle_timeout: Timeout inactivité (secondes)
            hard_timeout: Timeout absolu (secondes)
        """
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        
        if buffer_id:
            mod = parser.OFPFlowMod(
                datapath=datapath, 
                buffer_id=buffer_id,
                priority=priority, 
                match=match,
                instructions=inst, 
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath, 
                priority=priority,
                match=match, 
                instructions=inst,
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout
            )
        
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """
        Gère les paquets reçus par le contrôleur.
        Implémente l'apprentissage des adresses MAC.
        """
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        dpid = datapath.id

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        # Ignorer les paquets LLDP (Link Layer Discovery Protocol)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src

        # Filtres de sécurité supplémentaires
        if dst.startswith('33:33'):  # Multicast IPv6
            return
        if dst == 'ff:ff:ff:ff:ff:ff':  # Broadcast
            return
        if dst.startswith('01:00:5e'):  # Multicast IPv4
            return

        # Initialiser la table MAC pour ce switch
        self.mac_to_port.setdefault(dpid, {})

        # APPRENTISSAGE: Mémoriser le port source
        if src not in self.mac_to_port[dpid]:
            self.logger.info("📚 [s%d] APPRENTISSAGE: MAC %s détecté sur port %d", 
                           dpid, src, in_port)
            self.mac_to_port[dpid][src] = in_port
        else:
            # Mise à jour si le port a changé
            if self.mac_to_port[dpid][src] != in_port:
                self.logger.info("🔄 [s%d] MISE À JOUR: MAC %s déplacé vers port %d", 
                               dpid, src, in_port)
                self.mac_to_port[dpid][src] = in_port

        # FORWARDING: Déterminer le port de sortie
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
            self.logger.info("➡️  [s%d] FORWARD: %s → %s (port %d → port %d)", 
                           dpid, src[:8]+"...", dst[:8]+"...", in_port, out_port)
        else:
            out_port = ofproto.OFPP_FLOOD
            self.logger.info("🌊 [s%d] FLOOD: %s → %s (destination inconnue)", 
                           dpid, src[:8]+"...", dst[:8]+"...")

        actions = [parser.OFPActionOutput(out_port)]

        # Installer un flux permanent si la destination est connue
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            
            # Vérifier si le paquet est bufferisé
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 10, match, actions, msg.buffer_id,
                            idle_timeout=30, hard_timeout=60)
                self.logger.info("✅ [s%d] FLUX INSTALLÉ: %s → %s (idle=30s, hard=60s)", 
                               dpid, src[:8]+"...", dst[:8]+"...")
                return
            else:
                self.add_flow(datapath, 10, match, actions,
                            idle_timeout=30, hard_timeout=60)
                self.logger.info("✅ [s%d] FLUX INSTALLÉ: %s → %s (idle=30s, hard=60s)", 
                               dpid, src[:8]+"...", dst[:8]+"...")

        # Envoyer le paquet
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath, 
            buffer_id=msg.buffer_id,
            in_port=in_port, 
            actions=actions, 
            data=data
        )
        datapath.send_msg(out)
