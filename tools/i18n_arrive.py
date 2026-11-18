# NUTCADE translations for the notices when money arrives (src/app_arrive.js).
# Each row: English, Spanish, Portuguese (Brazil), German, French ("vous"). {#} stands for a number (kept as written,
# already grouped the language's way: 2,500 / 2.500 / 2 500).
# Run: python3 tools/i18n_arrive.py  ->  writes src/i18n_arrive.js, which adds these to the dictionaries in i18n.js.
ROWS = [
("Lightning deposit", "Depósito Lightning", "Depósito Lightning", "Lightning-Einzahlung", "Dépôt Lightning"),
("On-chain deposit", "Depósito on-chain", "Depósito on-chain", "On-Chain-Einzahlung", "Dépôt on-chain"),
("Wallet Connect invoice", "Factura de Wallet Connect", "Fatura do Wallet Connect", "Wallet-Connect-Rechnung", "Facture Wallet Connect"),
("Payment request paid", "Solicitud de pago pagada", "Pedido de pagamento pago", "Zahlungsanforderung bezahlt", "Demande de paiement payée"),
("Ecash over Nostr", "Ecash por Nostr", "Ecash via Nostr", "Ecash über Nostr", "Ecash par Nostr"),
("Ecash claimed", "Ecash reclamado", "Ecash resgatado", "Ecash eingelöst", "Ecash encaissé"),
("Came back to you", "Volvió a ti", "Voltou para você", "Zu dir zurückgekommen", "Vous est revenu"),
("MONEY ARRIVED", "LLEGÓ DINERO", "DINHEIRO RECEBIDO", "GELD EINGEGANGEN", "ARGENT REÇU"),
("Money arrived", "Llegó dinero", "Dinheiro recebido", "Geld eingegangen", "Argent reçu"),
("WHILE YOU WERE AWAY", "MIENTRAS NO ESTABAS", "ENQUANTO VOCÊ ESTAVA FORA", "WÄHREND DU WEG WARST", "PENDANT VOTRE ABSENCE"),
("While you were away", "Mientras no estabas", "Enquanto você estava fora", "Während du weg warst", "Pendant votre absence"),
("Since you last had NUTCADE open", "Desde la última vez que abriste NUTCADE", "Desde a última vez que você abriu o NUTCADE", "Seit du NUTCADE zuletzt geöffnet hattest", "Depuis la dernière ouverture de NUTCADE"),
("Total", "Total", "Total", "Gesamt", "Total"),
("{#} payment", "{#} pago", "{#} pagamento", "{#} Zahlung", "{#} paiement"),
("{#} payments", "{#} pagos", "{#} pagamentos", "{#} Zahlungen", "{#} paiements"),
("Open notes", "Abrir notas", "Abrir notas", "Notizen öffnen", "Ouvrir les notes"),
("Dismiss", "Cerrar", "Fechar", "Schließen", "Fermer"),
("Money arrived, unlock to see.", "Llegó dinero; desbloquea para verlo.", "Dinheiro recebido; desbloqueie para ver.", "Geld eingegangen, entsperre zum Ansehen.", "Argent reçu, déverrouillez pour voir."),
("Notify me when money arrives", "Avisarme cuando llegue dinero", "Avisar quando chegar dinheiro", "Benachrichtigen, wenn Geld eingeht", "Me prévenir quand de l'argent arrive"),
("When money arrives while NUTCADE is open in another tab or window. Shown by this device only: no push service, nothing is sent anywhere. While locked they show no amounts.",
 "Cuando llega dinero mientras NUTCADE está abierto en otra pestaña o ventana. Solo los muestra este dispositivo: sin servicio push, no se envía nada a ningún sitio. Con la cartera bloqueada no muestran importes.",
 "Quando chega dinheiro enquanto o NUTCADE está aberto em outra aba ou janela. Só este dispositivo as mostra: sem serviço de push, nada é enviado a lugar nenhum. Com a carteira bloqueada, não mostram valores.",
 "Wenn Geld eingeht, während NUTCADE in einem anderen Tab oder Fenster offen ist. Nur dieses Gerät zeigt sie an: kein Push-Dienst, nichts wird irgendwohin gesendet. Gesperrt zeigen sie keine Beträge.",
 "Quand de l'argent arrive alors que NUTCADE est ouvert dans un autre onglet ou une autre fenêtre. Affichées par cet appareil seulement : aucun service push, rien n'est envoyé nulle part. Verrouillé, elles n'affichent aucun montant."),
("Notifications are blocked for NUTCADE in this browser's settings. Allow them there, then turn this on.",
 "Las notificaciones de NUTCADE están bloqueadas en los ajustes de este navegador. Permítelas allí y luego activa esto.",
 "As notificações do NUTCADE estão bloqueadas nas configurações deste navegador. Permita-as lá e depois ative isto.",
 "Benachrichtigungen für NUTCADE sind in den Einstellungen dieses Browsers blockiert. Erlaube sie dort und schalte dies dann ein.",
 "Les notifications de NUTCADE sont bloquées dans les réglages de ce navigateur. Autorisez-les là, puis activez ceci."),
("Notifications weren't allowed. Turn this on to be asked again, or allow them in your browser's settings.",
 "No se permitieron las notificaciones. Activa esto para que se te vuelva a preguntar, o permítelas en los ajustes del navegador.",
 "As notificações não foram permitidas. Ative isto para ser perguntado de novo, ou permita-as nas configurações do navegador.",
 "Benachrichtigungen wurden nicht erlaubt. Schalte dies ein, um erneut gefragt zu werden, oder erlaube sie in den Browser-Einstellungen.",
 "Les notifications n'ont pas été autorisées. Activez ceci pour qu'on vous le redemande, ou autorisez-les dans les réglages du navigateur."),
("This browser can't show notifications.", "Este navegador no puede mostrar notificaciones.", "Este navegador não consegue mostrar notificações.", "Dieser Browser kann keine Benachrichtigungen anzeigen.", "Ce navigateur ne peut pas afficher de notifications."),
]

LANGS = ['es', 'pt', 'de', 'fr']

if __name__ == '__main__':
    import json, os
    seen = set()
    for row in ROWS:
        assert len(row) == 5, row
        assert row[0] not in seen, row[0]; seen.add(row[0])
        for x in row[1:]: assert row[0].count('{#}') == x.count('{#}'), row
    js = ['/* NUTCADE translations for the arrival notices, generated from tools/i18n_arrive.py: added to the dictionaries in i18n.js */', '(() => { const D = window.NUTCADE_I18N || {};']
    for i, l in enumerate(LANGS):
        t = {r[0]: r[i + 1] for r in ROWS}
        js.append('  if (D.%s) Object.assign(D.%s.t, %s);' % (l, l, json.dumps(t, ensure_ascii=False)))
    js.append('})();')
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "i18n_arrive.js")
    open(out, 'w').write('\n'.join(js) + '\n')
    print('rows', len(ROWS))
