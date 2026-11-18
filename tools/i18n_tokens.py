# NUTCADE translations for printable NUTCADE tokens and the logo in QR codes (src/app_tokens.js).
# Each row: English, Spanish, Portuguese (Brazil), German, French ("vous"). {#} stands for a number (kept as written).
# Run: python3 tools/i18n_tokens.py  ->  writes src/i18n_tokens.js, which adds these to the dictionaries in i18n.js.
ROWS = [
# --- the Print tokens screen ---
("Print tokens", "Imprimir tokens", "Imprimir tokens", "Tokens drucken", "Imprimer des jetons"),
("Hand sats over on paper, like arcade tokens. Each token is its own Cashu token with its own QR code: whoever scans it first gets its sats, with any Cashu wallet.",
 "Entrega sats en papel, como fichas de arcade. Cada token es un token Cashu propio con su propio código QR: quien lo escanee primero se lleva sus sats, con cualquier billetera Cashu.",
 "Entregue sats em papel, como fichas de fliperama. Cada token é um token Cashu próprio, com seu próprio QR code: quem escanear primeiro leva os sats, com qualquer carteira Cashu.",
 "Gib Sats auf Papier weiter, wie Spielhallen-Münzen. Jedes Token ist ein eigenes Cashu-Token mit eigenem QR-Code: Wer es zuerst scannt, bekommt seine Sats, mit jeder Cashu-Wallet.",
 "Remettez des sats sur papier, comme des jetons d'arcade. Chaque jeton est un jeton Cashu à part, avec son propre QR code : la première personne qui le scanne reçoit ses sats, avec n'importe quel portefeuille Cashu."),
("Amount per token (SAT)", "Cantidad por token (SAT)", "Valor por token (SAT)", "Betrag pro Token (SAT)", "Montant par jeton (SAT)"),
("How many (1 to 20)", "Cuántos (1 a 20)", "Quantos (1 a 20)", "Wie viele (1 bis 20)", "Combien (1 à 20)"),
("Style", "Estilo", "Estilo", "Stil", "Style"),
("INK SAVER", "AHORRA TINTA", "ECONOMIZA TINTA", "TINTE SPAREN", "ÉCO ENCRE"),
("Ink saver", "Ahorra tinta", "Economiza tinta", "Tinte sparen", "Éco encre"),
("Black on white.", "Negro sobre blanco.", "Preto no branco.", "Schwarz auf Weiß.", "Noir sur blanc."),
("Full color. The QR code is always dark on light.", "A todo color. El código QR siempre es oscuro sobre claro.", "Colorido. O QR code é sempre escuro sobre claro.", "In Farbe. Der QR-Code ist immer dunkel auf hell.", "En couleurs. Le QR code est toujours foncé sur clair."),
("Next", "Siguiente", "Avançar", "Weiter", "Suivant"),
("Printed tokens ({#})", "Tokens impresos ({#})", "Tokens impressos ({#})", "Gedruckte Tokens ({#})", "Jetons imprimés ({#})"),
("Pick how many tokens: 1 to 20.", "Elige cuántos tokens: de 1 a 20.", "Escolha quantos tokens: de 1 a 20.", "Wähle, wie viele Tokens: 1 bis 20.", "Choisissez combien de jetons : de 1 à 20."),
("Making tokens needs the mint, and you're offline. Try again online.", "Crear tokens necesita el mint y estás sin conexión. Vuelve a intentarlo con conexión.", "Criar tokens precisa do mint, e você está offline. Tente de novo online.", "Zum Erstellen von Tokens braucht es den Mint, und du bist offline. Versuch es online noch einmal.", "Créer des jetons nécessite le mint, et vous êtes hors ligne. Réessayez en ligne."),
("{#} × {#} SAT plus the mint's fees is more than this mint holds ({#} SAT).", "{#} × {#} SAT más las comisiones del mint es más de lo que tiene este mint ({#} SAT).", "{#} × {#} SAT mais as taxas do mint é mais do que este mint tem ({#} SAT).", "{#} × {#} SAT plus die Gebühren des Mints ist mehr, als dieser Mint hält ({#} SAT).", "{#} × {#} SAT plus les frais du mint, c'est plus que ce que contient ce mint ({#} SAT)."),
("Tokens", "Tokens", "Tokens", "Tokens", "Jetons"),
("{#} × {#} SAT", "{#} × {#} SAT", "{#} × {#} SAT", "{#} × {#} SAT", "{#} × {#} SAT"),
("Total", "Total", "Total", "Summe", "Total"),
("Fees", "Comisiones", "Taxas", "Gebühren", "Frais"),
("up to {#} SAT", "hasta {#} SAT", "até {#} SAT", "bis zu {#} SAT", "jusqu'à {#} SAT"),
("None at this mint", "Ninguna en este mint", "Nenhuma neste mint", "Keine bei diesem Mint", "Aucun sur ce mint"),
("The mint's fee for making each token, and the fee each token carries so whoever claims it gets the full {#} SAT.",
 "La comisión del mint por crear cada token, y la comisión que lleva cada token para que quien lo reclame reciba los {#} SAT completos.",
 "A taxa do mint para criar cada token, e a taxa que cada token leva para que quem o resgatar receba os {#} SAT inteiros.",
 "Die Gebühr des Mints für jedes Token und die Gebühr, die jedes Token mitbringt, damit die einlösende Person die vollen {#} SAT bekommt.",
 "Les frais du mint pour créer chaque jeton, et les frais que chaque jeton emporte pour que la personne qui le réclame reçoive les {#} SAT entiers."),
("The sats leave your balance now. Unclaimed tokens can be taken back any time from Printed tokens. A photo of a code is enough to take its sats, so keep them hidden until you hand them over.",
 "Los sats salen de tu saldo ahora. Los tokens sin reclamar se pueden recuperar cuando quieras desde Tokens impresos. Una foto de un código basta para llevarse sus sats, así que mantenlos ocultos hasta entregarlos.",
 "Os sats saem do seu saldo agora. Tokens não resgatados podem ser pegos de volta a qualquer momento em Tokens impressos. Uma foto do código basta para levar os sats, então mantenha-os escondidos até entregá-los.",
 "Die Sats verlassen jetzt dein Guthaben. Nicht eingelöste Tokens kannst du jederzeit unter Gedruckte Tokens zurückholen. Ein Foto eines Codes reicht, um seine Sats zu nehmen, also halte sie verdeckt, bis du sie übergibst.",
 "Les sats quittent votre solde maintenant. Les jetons non réclamés peuvent être repris à tout moment depuis Jetons imprimés. Une photo d'un code suffit pour prendre ses sats : gardez-les cachés jusqu'à ce que vous les remettiez."),
("Make 1 token", "Crear 1 token", "Criar 1 token", "1 Token erstellen", "Créer 1 jeton"),
("Make {#} tokens", "Crear {#} tokens", "Criar {#} tokens", "{#} Tokens erstellen", "Créer {#} jetons"),
("MAKING TOKENS", "CREANDO TOKENS", "CRIANDO TOKENS", "ERSTELLE TOKENS", "CRÉATION DES JETONS"),
("MAKING TOKEN {#} OF {#}", "CREANDO TOKEN {#} DE {#}", "CRIANDO TOKEN {#} DE {#}", "ERSTELLE TOKEN {#} VON {#}", "CRÉATION DU JETON {#} SUR {#}"),
("CHECKING CODES", "COMPROBANDO CÓDIGOS", "VERIFICANDO CÓDIGOS", "PRÜFE CODES", "VÉRIFICATION DES CODES"),
("TAKING BACK", "RECUPERANDO", "PEGANDO DE VOLTA", "HOLE ZURÜCK", "REPRISE"),
("{#} of {#} tokens were made before this. They are in Printed tokens: print them or take them back.",
 "Antes de esto se crearon {#} de {#} tokens. Están en Tokens impresos: imprímelos o recupéralos.",
 "{#} de {#} tokens foram criados antes disso. Eles estão em Tokens impressos: imprima-os ou pegue-os de volta.",
 "{#} von {#} Tokens wurden vorher erstellt. Sie sind unter Gedruckte Tokens: drucke sie oder hol sie zurück.",
 "{#} jetons sur {#} ont été créés avant cela. Ils sont dans Jetons imprimés : imprimez-les ou reprenez-les."),
("Every token of this batch was claimed or taken back, so there is nothing to print.", "Todos los tokens de este lote se reclamaron o recuperaron, así que no hay nada que imprimir.", "Todos os tokens deste lote foram resgatados ou pegos de volta, então não há nada para imprimir.", "Jedes Token dieses Stapels wurde eingelöst oder zurückgeholt, es gibt nichts zu drucken.", "Tous les jetons de ce lot ont été réclamés ou repris : il n'y a rien à imprimer."),
("1 TOKEN READY", "1 TOKEN LISTO", "1 TOKEN PRONTO", "1 TOKEN BEREIT", "1 JETON PRÊT"),
("{#} TOKENS READY", "{#} TOKENS LISTOS", "{#} TOKENS PRONTOS", "{#} TOKENS BEREIT", "{#} JETONS PRÊTS"),
("Fees paid", "Comisiones pagadas", "Taxas pagas", "Bezahlte Gebühren", "Frais payés"),
("✓ Every code was read back and scans.", "✓ Cada código se volvió a leer y se puede escanear.", "✓ Cada código foi lido de volta e pode ser escaneado.", "✓ Jeder Code wurde zurückgelesen und lässt sich scannen.", "✓ Chaque code a été relu et se scanne."),
("Cut along the dashed lines. Fold each card on the dotted line, printed sides out: front and back of one token. Fold it the other way to keep the code hidden until you hand it over.",
 "Corta por las líneas discontinuas. Dobla cada tarjeta por la línea de puntos, con lo impreso hacia fuera: anverso y reverso de un token. Dóblala al revés para mantener el código oculto hasta entregarlo.",
 "Corte nas linhas tracejadas. Dobre cada cartão na linha pontilhada, com a impressão para fora: frente e verso de um token. Dobre ao contrário para manter o código escondido até entregá-lo.",
 "Schneide entlang der gestrichelten Linien. Falte jede Karte an der gepunkteten Linie, bedruckte Seiten nach außen: Vorder- und Rückseite eines Tokens. Falte sie andersherum, um den Code bis zur Übergabe zu verdecken.",
 "Découpez le long des tirets. Pliez chaque carte sur la ligne pointillée, faces imprimées vers l'extérieur : le recto et le verso d'un jeton. Pliez-la dans l'autre sens pour garder le code caché jusqu'à ce que vous le remettiez."),
("Print", "Imprimir", "Imprimir", "Drucken", "Imprimer"),
("BEFORE YOU PRINT", "ANTES DE IMPRIMIR", "ANTES DE IMPRIMIR", "BEVOR DU DRUCKST", "AVANT D'IMPRIMER"),
("A printed token is cash. Whoever scans it first gets the sats. Keep it folded or hidden until you hand it over.",
 "Un token impreso es dinero en efectivo. Quien lo escanee primero se lleva los sats. Mantenlo doblado u oculto hasta entregarlo.",
 "Um token impresso é dinheiro vivo. Quem escanear primeiro leva os sats. Mantenha-o dobrado ou escondido até entregá-lo.",
 "Ein gedrucktes Token ist Bargeld. Wer es zuerst scannt, bekommt die Sats. Halte es gefaltet oder verdeckt, bis du es übergibst.",
 "Un jeton imprimé, c'est de l'argent liquide. La première personne qui le scanne reçoit les sats. Gardez-le plié ou caché jusqu'à ce que vous le remettiez."),
("I understand", "Entendido", "Entendi", "Verstanden", "J'ai compris"),
("Amount per token", "Cantidad por token", "Valor por token", "Betrag pro Token", "Montant par jeton"),
("OTHER", "OTRA", "OUTRO", "ANDERER", "AUTRE"),
("{#} SAT would need {#} coins here, too dense to scan reliably on paper.", "{#} SAT necesitaría {#} monedas aquí, demasiado denso para escanearse bien en papel.", "{#} SAT precisaria de {#} moedas aqui, denso demais para escanear bem no papel.", "{#} SAT bräuchte hier {#} Münzen, zu dicht, um auf Papier zuverlässig gescannt zu werden.", "{#} SAT nécessiterait {#} pièces ici, trop dense pour se scanner de façon fiable sur papier."),
("Nobody claimed it? Take it back any time in", "¿Nadie lo reclamó? Recupéralo cuando quieras en", "Ninguém resgatou? Pegue de volta quando quiser em", "Niemand hat es eingelöst? Hol es jederzeit zurück unter", "Personne ne l'a réclamé ? Reprenez-le quand vous voulez dans"),
("Notes → Printed tokens", "Notas → Tokens impresos", "Notas → Tokens impressos", "Notizen → Gedruckte Tokens", "Notes → Jetons imprimés"),
("STOPPED AFTER {#} OF {#}", "DETENIDO TRAS {#} DE {#}", "PARADO DEPOIS DE {#} DE {#}", "GESTOPPT NACH {#} VON {#}", "ARRÊTÉ APRÈS {#} SUR {#}"),
("Nothing more was made.", "No se creó nada más.", "Nada mais foi criado.", "Mehr wurde nicht erstellt.", "Rien de plus n'a été créé."),
("Print what was made", "Imprimir lo creado", "Imprimir o que foi criado", "Erstelltes drucken", "Imprimer ce qui a été créé"),
("Your balance changed since, so the cost was worked out again. Check it and tap Make again.", "Tu saldo cambió desde entonces, así que se volvió a calcular el coste. Revísalo y vuelve a tocar Crear.", "Seu saldo mudou desde então, então o custo foi recalculado. Confira e toque em Criar de novo.", "Dein Guthaben hat sich seitdem geändert, daher wurden die Kosten neu berechnet. Prüfe sie und tippe noch einmal auf Erstellen.", "Votre solde a changé entre-temps : le coût a été recalculé. Vérifiez-le et touchez à nouveau Créer."),
("Another payment changed the coins at this mint during the batch, so the next token would cost more than shown.", "Otro pago cambió las monedas de este mint durante el lote, así que el siguiente token costaría más de lo indicado.", "Outro pagamento mudou as moedas deste mint durante o lote, então o próximo token custaria mais do que o mostrado.", "Eine andere Zahlung hat während des Stapels die Münzen bei diesem Mint verändert, das nächste Token würde mehr kosten als angezeigt.", "Un autre paiement a modifié les pièces de ce mint pendant le lot : le jeton suivant coûterait plus que prévu."),
("These coins are no longer here. Nothing was sent.", "Estas monedas ya no están aquí. No se envió nada.", "Essas moedas não estão mais aqui. Nada foi enviado.", "Diese Münzen sind nicht mehr da. Es wurde nichts gesendet.", "Ces pièces ne sont plus là. Rien n'a été envoyé."),
("A {#} SAT token needs {#} coins, and its QR code would be too dense to scan reliably on paper. Pick an amount made of fewer coins: {#} or {#} are one coin each, {#} is six.",
 "Un token de {#} SAT necesita {#} monedas, y su código QR sería demasiado denso para escanearse bien en papel. Elige una cantidad con menos monedas: {#} o {#} son una moneda cada una, {#} son seis.",
 "Um token de {#} SAT precisa de {#} moedas, e o QR code ficaria denso demais para escanear bem no papel. Escolha um valor com menos moedas: {#} ou {#} são uma moeda cada, {#} são seis.",
 "Ein Token über {#} SAT braucht {#} Münzen, und sein QR-Code wäre zu dicht, um auf Papier zuverlässig gescannt zu werden. Wähle einen Betrag aus weniger Münzen: {#} oder {#} sind je eine Münze, {#} sind sechs.",
 "Un jeton de {#} SAT nécessite {#} pièces, et son QR code serait trop dense pour se scanner de façon fiable sur papier. Choisissez un montant fait de moins de pièces : {#} ou {#} font une pièce chacun, {#} en fait six."),
("Make the tokens again to print them.", "Vuelve a preparar los tokens para imprimirlos.", "Prepare os tokens de novo para imprimi-los.", "Bereite die Tokens erneut vor, um sie zu drucken.", "Préparez à nouveau les jetons pour les imprimer."),
# --- on paper ---
("TOKEN", "TOKEN", "TOKEN", "TOKEN", "JETON"),
("Mint:", "Mint:", "Mint:", "Mint:", "Mint :"),
("Made", "Hecho el", "Feito em", "Erstellt", "Créé le"),
("Token", "Token", "Token", "Token", "Jeton"),
("SCAN TO CLAIM", "ESCANEA PARA RECLAMAR", "ESCANEIE PARA RESGATAR", "SCANNEN ZUM EINLÖSEN", "SCANNEZ POUR RÉCLAMER"),
("HOW TO CLAIM", "CÓMO RECLAMAR", "COMO RESGATAR", "SO LÖST DU EIN", "COMMENT RÉCLAMER"),
("Open any Cashu wallet (NUTCADE, Minibits, cashu.me…).", "Abre cualquier billetera Cashu (NUTCADE, Minibits, cashu.me…).", "Abra qualquer carteira Cashu (NUTCADE, Minibits, cashu.me…).", "Öffne eine beliebige Cashu-Wallet (NUTCADE, Minibits, cashu.me…).", "Ouvrez n'importe quel portefeuille Cashu (NUTCADE, Minibits, cashu.me…)."),
("Scan the code on the front. The sats are now yours.", "Escanea el código del anverso. Los sats ya son tuyos.", "Escaneie o código da frente. Os sats agora são seus.", "Scanne den Code auf der Vorderseite. Die Sats gehören jetzt dir.", "Scannez le code au recto. Les sats sont à vous."),
("New to this? Open", "¿Nuevo en esto? Abre", "Primeira vez? Abra", "Neu dabei? Öffne", "Première fois ? Ouvrez"),
("This token IS the money. Whoever scans it first gets the sats. Keep the code hidden until you hand it over.",
 "Este token ES el dinero. Quien lo escanee primero se lleva los sats. Mantén el código oculto hasta entregarlo.",
 "Este token É o dinheiro. Quem escanear primeiro leva os sats. Mantenha o código escondido até entregá-lo.",
 "Dieses Token IST das Geld. Wer es zuerst scannt, bekommt die Sats. Halte den Code verdeckt, bis du es übergibst.",
 "Ce jeton EST l'argent. La première personne qui le scanne reçoit les sats. Gardez le code caché jusqu'à ce que vous le remettiez."),
("CHECK IT'S STILL GOOD: SCAN IN NUTCADE", "COMPRUEBA QUE SIGUE VÁLIDO: ESCANÉALO EN NUTCADE", "VEJA SE AINDA VALE: ESCANEIE NO NUTCADE", "NOCH GÜLTIG? IN NUTCADE SCANNEN", "TOUJOURS VALABLE ? SCANNEZ DANS NUTCADE"),
("NO ACCOUNT. NO TRACKING.", "SIN CUENTA. SIN RASTREO.", "SEM CONTA. SEM RASTREAMENTO.", "KEIN KONTO. KEIN TRACKING.", "SANS COMPTE. SANS PISTAGE."),
# --- the Printed tokens list ---
("Printed tokens", "Tokens impresos", "Tokens impressos", "Gedruckte Tokens", "Jetons imprimés"),
("{#} printed · {#} unclaimed · {#} claimed · {#} taken back", "{#} impresos · {#} sin reclamar · {#} reclamados · {#} recuperados", "{#} impressos · {#} não resgatados · {#} resgatados · {#} pegos de volta", "{#} gedruckt · {#} nicht eingelöst · {#} eingelöst · {#} zurückgeholt", "{#} imprimés · {#} non réclamés · {#} réclamés · {#} repris"),
("Take back all unclaimed", "Recuperar todos los no reclamados", "Pegar de volta todos não resgatados", "Alle nicht eingelösten zurückholen", "Reprendre tous les non réclamés"),
("Print again", "Imprimir de nuevo", "Imprimir de novo", "Erneut drucken", "Imprimer à nouveau"),
("UNCLAIMED", "SIN RECLAMAR", "NÃO RESGATADO", "NICHT EINGELÖST", "NON RÉCLAMÉ"),
("TAKEN BACK", "RECUPERADO", "DE VOLTA", "ZURÜCKGEHOLT", "REPRIS"),
("Take back", "Recuperar", "Pegar de volta", "Zurückholen", "Reprendre"),
("No printed tokens yet.", "Aún no hay tokens impresos.", "Ainda não há tokens impressos.", "Noch keine gedruckten Tokens.", "Pas encore de jetons imprimés."),
("{#} claimed since the last check", "{#} reclamados desde la última comprobación", "{#} resgatados desde a última verificação", "{#} seit der letzten Prüfung eingelöst", "{#} réclamés depuis la dernière vérification"),
("No new claims", "Ningún reclamo nuevo", "Nenhum resgate novo", "Keine neuen Einlösungen", "Aucune nouvelle réclamation"),
("Token taken back", "Token recuperado", "Token pego de volta", "Token zurückgeholt", "Jeton repris"),
("1 token taken back", "1 token recuperado", "1 token pego de volta", "1 Token zurückgeholt", "1 jeton repris"),
("{#} tokens taken back", "{#} tokens recuperados", "{#} tokens pegos de volta", "{#} Tokens zurückgeholt", "{#} jetons repris"),
("1 token couldn't be taken back.", "No se pudo recuperar 1 token.", "Não foi possível pegar de volta 1 token.", "1 Token ließ sich nicht zurückholen.", "1 jeton n'a pas pu être repris."),
("{#} tokens couldn't be taken back.", "No se pudieron recuperar {#} tokens.", "Não foi possível pegar de volta {#} tokens.", "{#} Tokens ließen sich nicht zurückholen.", "{#} jetons n'ont pas pu être repris."),
("PRINTED", "IMPRESO", "IMPRESSO", "GEDRUCKT", "IMPRIMÉ"),
("Printed token", "Token impreso", "Token impresso", "Gedrucktes Token", "Jeton imprimé"),
("Printed token {#} of {#}", "Token impreso {#} de {#}", "Token impresso {#} de {#}", "Gedrucktes Token {#} von {#}", "Jeton imprimé {#} sur {#}"),
# --- the QR code center ---
("QR code center", "Centro del código QR", "Centro do QR code", "QR-Code-Mitte", "Centre du QR code"),
("NONE", "NINGUNO", "NENHUM", "KEINS", "AUCUN"),
("NUTCADE ACORN", "BELLOTA NUTCADE", "BOLOTA NUTCADE", "NUTCADE-EICHEL", "GLAND NUTCADE"),
("The acorn in the middle of the QR codes NUTCADE shows and prints. A code that wouldn't scan with it shows plain, and animated codes stay plain.",
 "La bellota en el centro de los códigos QR que NUTCADE muestra e imprime. Un código que no se pueda escanear con ella se muestra sin nada, y los códigos animados siguen sin nada.",
 "A bolota no centro dos QR codes que o NUTCADE mostra e imprime. Um código que não escanearia com ela aparece simples, e códigos animados continuam simples.",
 "Die Eichel in der Mitte der QR-Codes, die NUTCADE zeigt und druckt. Ein Code, der damit nicht scannbar wäre, erscheint ohne, und animierte Codes bleiben ohne.",
 "Le gland au centre des QR codes que NUTCADE affiche et imprime. Un code qui ne se scannerait pas avec lui s'affiche sans, et les codes animés restent sans."),
]

# Sentences with a token number, a mint or a list in them: $1 is put back (translated when it is a sentence itself)
RE = [
(r"^Token #(\S+) is too long for one printed QR code, so nothing was printed\. It is kept in Printed tokens: take it back, or send it another way\.$",
 "El token #$1 es demasiado largo para un solo código QR impreso, así que no se imprimió nada. Queda en Tokens impresos: recupéralo o envíalo de otra forma.",
 "O token #$1 é longo demais para um único QR code impresso, então nada foi impresso. Ele fica em Tokens impressos: pegue-o de volta ou envie de outro jeito.",
 "Token #$1 ist zu lang für einen gedruckten QR-Code, daher wurde nichts gedruckt. Es bleibt unter Gedruckte Tokens: hol es zurück oder sende es anders.",
 "Le jeton #$1 est trop long pour un seul QR code imprimé : rien n'a été imprimé. Il reste dans Jetons imprimés : reprenez-le, ou envoyez-le autrement."),
(r"^The QR code of token #(\S+) didn't read back, so nothing was printed\. Your tokens are kept in Printed tokens: try printing again, or take them back\.$",
 "El código QR del token #$1 no se pudo volver a leer, así que no se imprimió nada. Tus tokens quedan en Tokens impresos: intenta imprimir de nuevo o recupéralos.",
 "O QR code do token #$1 não pôde ser lido de volta, então nada foi impresso. Seus tokens ficam em Tokens impressos: tente imprimir de novo ou pegue-os de volta.",
 "Der QR-Code von Token #$1 ließ sich nicht zurücklesen, daher wurde nichts gedruckt. Deine Tokens bleiben unter Gedruckte Tokens: versuch erneut zu drucken oder hol sie zurück.",
 "Le QR code du jeton #$1 n'a pas pu être relu : rien n'a été imprimé. Vos jetons restent dans Jetons imprimés : réessayez d'imprimer, ou reprenez-les."),
(r"^Someone already claimed token #(\S+), so there is nothing to take back\. Your balance didn't change\.$",
 "Alguien ya reclamó el token #$1, así que no hay nada que recuperar. Tu saldo no cambió.",
 "Alguém já resgatou o token #$1, então não há nada para pegar de volta. Seu saldo não mudou.",
 "Jemand hat Token #$1 schon eingelöst, es gibt nichts zurückzuholen. Dein Guthaben hat sich nicht geändert.",
 "Quelqu'un a déjà réclamé le jeton #$1 : il n'y a rien à reprendre. Votre solde n'a pas changé."),
(r"^Couldn't reach (.+)\. Nothing changed for its tokens: check again when it answers\.$",
 "No se pudo contactar con $1. Nada cambió para sus tokens: vuelve a comprobar cuando responda.",
 "Não foi possível alcançar $1. Nada mudou para os tokens dele: verifique de novo quando ele responder.",
 "$1 war nicht erreichbar. Für seine Tokens hat sich nichts geändert: prüfe erneut, wenn er antwortet.",
 "Impossible de joindre $1. Rien n'a changé pour ses jetons : vérifiez à nouveau quand il répondra."),
(r"^The QR code of token #(\S+) is too dense to scan reliably on paper, so nothing was printed\. It is kept in Printed tokens: take it back, or send it another way\.$",
 "El código QR del token #$1 es demasiado denso para escanearse bien en papel, así que no se imprimió nada. Queda en Tokens impresos: recupéralo o envíalo de otra forma.",
 "O QR code do token #$1 é denso demais para escanear bem no papel, então nada foi impresso. Ele fica em Tokens impressos: pegue-o de volta ou envie de outro jeito.",
 "Der QR-Code von Token #$1 ist zu dicht, um auf Papier zuverlässig gescannt zu werden, daher wurde nichts gedruckt. Es bleibt unter Gedruckte Tokens: hol es zurück oder sende es anders.",
 "Le QR code du jeton #$1 est trop dense pour se scanner de façon fiable sur papier : rien n'a été imprimé. Il reste dans Jetons imprimés : reprenez-le, ou envoyez-le autrement."),
(r"^(.+) takes too few coins per request to print tokens from it\.$", "$1 acepta muy pocas monedas por solicitud para imprimir tokens desde él.", "$1 aceita poucas moedas por pedido para imprimir tokens a partir dele.", "$1 nimmt zu wenige Münzen pro Anfrage an, um davon Tokens zu drucken.", "$1 accepte trop peu de pièces par requête pour imprimer des jetons depuis ce mint."),
(r"^QR code of token #(\S+)$", "Código QR del token #$1", "QR code do token #$1", "QR-Code von Token #$1", "QR code du jeton #$1"),
]

LANGS = ['es', 'pt', 'de', 'fr']
NUM = r'\d(?:[\d,.  ]*\d)?'
def numpat(p):
    return p.replace(r'[\d,]+', NUM).replace(r'\d+', NUM)

if __name__ == '__main__':
    import json, os
    seen = set()
    for row in ROWS:
        assert len(row) == 5, row
        assert row[0] not in seen, row[0]; seen.add(row[0])
        for x in row[1:]: assert row[0].count('{#}') == x.count('{#}'), row
    import re as _re
    here = os.path.dirname(os.path.abspath(__file__))
    old = open(os.path.join(here, '..', 'src', 'i18n.js')).read() + open(os.path.join(here, '..', 'src', 'i18n_r4.js')).read()
    for row in ROWS:   # (a text other screens already show is translated there: one meaning per text)
        assert json.dumps(row[0], ensure_ascii=False) + ':' not in old, 'already translated elsewhere: ' + row[0]
    for row in RE:
        assert len(row) == 5, row
        for x in row[1:]: assert x.count('$1') == 1, row
    js = ['/* NUTCADE printable tokens + QR logo translations, generated from tools/i18n_tokens.py: added to the dictionaries in i18n.js */', '(() => { const D = window.NUTCADE_I18N || {};']
    for i, l in enumerate(LANGS):
        t = {r[0]: r[i + 1] for r in ROWS}
        pats = ', '.join('[new RegExp(%s), %s]' % (json.dumps(numpat(p[0])), json.dumps(p[i + 1], ensure_ascii=False)) for p in RE)
        js.append('  if (D.%s) { Object.assign(D.%s.t, %s); D.%s.re = [%s].concat(D.%s.re || []); }' % (l, l, json.dumps(t, ensure_ascii=False), l, pats, l))
    js.append('})();')
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "i18n_tokens.js")
    open(out, 'w').write('\n'.join(js) + '\n')
    print('rows', len(ROWS), 'patterns', len(RE))
