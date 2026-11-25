# NUTCADE Daily Challenge translations: en, es, pt (Brazil), de, fr (French uses "vous", German "Du").
# Run: python3 tools/i18n_daily.py  ->  writes src/i18n_daily.js, which adds these to the dictionaries in i18n.js.
# {a} {d} {g} {h} {k} {m} {n} {r} {s} {t} are filled in by daily.js after translating (dates and numbers are already
# written the language's way), so each translation must keep the same placeholders as the English.
# A key that i18n.js or i18n_r4.js already has is left as it is.
import json, os, re
NB = ' '
ROWS = [
("DAILY CHALLENGE", "RETO DIARIO", "DESAFIO DIÁRIO", "TAGES-CHALLENGE", "DÉFI DU JOUR"),
("DAILY", "DIARIO", "DIÁRIO", "TÄGLICH", "DÉFI"),
("TODAY'S SCORE", "PUNTOS DE HOY", "PONTOS DE HOJE", "PUNKTE HEUTE", "SCORE DU JOUR"),
("NOT PLAYED YET", "AÚN SIN JUGAR", "AINDA NÃO JOGADO", "NOCH NICHT GESPIELT", "PAS ENCORE JOUÉ"),
("First run of the day counts. Replay for fun after that.", "La primera partida del día cuenta. Después, repite por diversión.", "A primeira partida do dia conta. Depois, jogue de novo por diversão.", "Der erste Lauf des Tages zählt. Danach kannst Du zum Spaß wiederholen.", "La première partie du jour compte. Ensuite, rejouez pour le plaisir."),
("Best today for fun: {s}", "Mejor de hoy por diversión: {s}", "Melhor de hoje por diversão: {s}", "Bestwert heute zum Spaß: {s}", "Meilleur score du jour pour le plaisir" + NB + ": {s}"),
("No streak yet", "Aún sin racha", "Ainda sem sequência", "Noch keine Serie", "Pas encore de série"),
("Streak: {n} day", "Racha: {n} día", "Sequência: {n} dia", "Serie: {n} Tag", "Série" + NB + ": {n} jour"),
("Streak: {n} days", "Racha: {n} días", "Sequência: {n} dias", "Serie: {n} Tage", "Série" + NB + ": {n} jours"),
("Best streak: {n}", "Mejor racha: {n}", "Melhor sequência: {n}", "Beste Serie: {n}", "Meilleure série" + NB + ": {n}"),
("Your device clock looks wrong. You can still play for fun, but runs don't count as official or toward your streak until it's fixed.", "El reloj de tu dispositivo parece estar mal. Aún puedes jugar por diversión, pero las partidas no cuentan como oficiales ni para tu racha hasta que se arregle.", "O relógio do seu dispositivo parece estar errado. Você ainda pode jogar por diversão, mas as partidas não contam como oficiais nem para a sua sequência até ele ser corrigido.", "Die Uhr Deines Geräts scheint falsch zu gehen. Du kannst weiter zum Spaß spielen, aber die Läufe zählen nicht als offiziell oder für Deine Serie, bis sie korrigiert ist.", "L'horloge de votre appareil semble incorrecte. Vous pouvez toujours jouer pour le plaisir, mais les parties ne comptent ni comme officielles ni pour votre série tant qu'elle n'est pas corrigée."),
("My clock is right", "Mi reloj es correcto", "Meu relógio está certo", "Meine Uhr stimmt", "Mon horloge est correcte"),
("{h}h {m}m", "{h} h {m} min", "{h} h {m} min", "{h} Std. {m} Min.", "{h} h {m} min"),
("{m}m", "{m} min", "{m} min", "{m} Min.", "{m} min"),
("Next challenge in {a}", "Próximo reto en {a}", "Próximo desafio em {a}", "Nächste Challenge in {a}", "Prochain défi dans {a}"),
("New one at {t} your time (midnight UTC)", "El nuevo llega a las {t} de tu hora (medianoche UTC)", "O novo chega às {t} no seu horário (meia-noite UTC)", "Die neue kommt um {t} Deiner Zeit (Mitternacht UTC)", "Le prochain arrive à {t}, heure locale (minuit UTC)"),
("PLAY DAILY", "JUGAR EL RETO", "JOGAR O DESAFIO", "CHALLENGE SPIELEN", "JOUER LE DÉFI"),
("PLAY FOR FUN", "JUGAR POR DIVERSIÓN", "JOGAR POR DIVERSÃO", "ZUM SPASS SPIELEN", "JOUER POUR LE PLAISIR"),
("Play the daily challenge: {g}", "Jugar el reto diario: {g}", "Jogar o desafio diário: {g}", "Tages-Challenge spielen: {g}", "Jouer le défi du jour" + NB + ": {g}"),
("Share my score", "Compartir mi puntuación", "Compartilhar minha pontuação", "Meine Punkte teilen", "Partager mon score"),
("History", "Historial", "Histórico", "Verlauf", "Historique"),
("Daily history", "Historial diario", "Histórico diário", "Tagesverlauf", "Historique du défi"),
("NO DAILY RUNS YET", "AÚN NO HAY PARTIDAS DIARIAS", "AINDA SEM PARTIDAS DIÁRIAS", "NOCH KEINE TAGESLÄUFE", "PAS ENCORE DE PARTIES DU JOUR"),
("Your first run of each day is your official score.", "Tu primera partida de cada día es tu puntuación oficial.", "Sua primeira partida de cada dia é a sua pontuação oficial.", "Dein erster Lauf jedes Tages ist Dein offizielles Ergebnis.", "Votre première partie de chaque jour est votre score officiel."),
("Preview of your note", "Vista previa de tu nota", "Prévia da sua nota", "Vorschau Deiner Notiz", "Aperçu de votre note"),
("Posts a public note on Nostr, signed with your NUTCADE key ({k}), to your {r}. Nothing is sent until you tap Post.", "Publica una nota pública en Nostr, firmada con tu clave de NUTCADE ({k}), en tus {r}. No se envía nada hasta que toques Publicar.", "Publica uma nota pública no Nostr, assinada com a sua chave do NUTCADE ({k}), nos seus {r}. Nada é enviado até você tocar em Publicar.", "Veröffentlicht eine öffentliche Notiz auf Nostr, signiert mit Deinem NUTCADE-Schlüssel ({k}), an Deine {r}. Nichts wird gesendet, bis Du auf Posten tippst.", "Publie une note publique sur Nostr, signée avec votre clé NUTCADE ({k}), sur vos {r}. Rien n'est envoyé tant que vous n'appuyez pas sur Publier."),
("Posts a public note on Nostr, signed with your NUTCADE key ({k}), to your relay. Nothing is sent until you tap Post.", "Publica una nota pública en Nostr, firmada con tu clave de NUTCADE ({k}), en tu relé. No se envía nada hasta que toques Publicar.", "Publica uma nota pública no Nostr, assinada com a sua chave do NUTCADE ({k}), no seu relay. Nada é enviado até você tocar em Publicar.", "Veröffentlicht eine öffentliche Notiz auf Nostr, signiert mit Deinem NUTCADE-Schlüssel ({k}), an Dein Relay. Nichts wird gesendet, bis Du auf Posten tippst.", "Publie une note publique sur Nostr, signée avec votre clé NUTCADE ({k}), sur votre relais. Rien n'est envoyé tant que vous n'appuyez pas sur Publier."),   # one relay: the plural sentence below says "your 3 relays", which can't be reused for 1
("Posts a public note on Nostr, signed with your Nostr identity ({k}), to your {r}. Nothing is sent until you tap Post.", "Publica una nota pública en Nostr, firmada con tu identidad de Nostr ({k}), en tus {r}. No se envía nada hasta que toques Publicar.", "Publica uma nota pública no Nostr, assinada com a sua identidade Nostr ({k}), nos seus {r}. Nada é enviado até você tocar em Publicar.", "Veröffentlicht eine öffentliche Notiz auf Nostr, signiert mit Deiner Nostr-Identität ({k}), an Deine {r}. Nichts wird gesendet, bis Du auf Posten tippst.", "Publie une note publique sur Nostr, signée avec votre identité Nostr ({k}), sur vos {r}. Rien n'est envoyé tant que vous n'appuyez pas sur Publier."),
("Posts a public note on Nostr, signed with your Nostr identity ({k}), to your relay. Nothing is sent until you tap Post.", "Publica una nota pública en Nostr, firmada con tu identidad de Nostr ({k}), en tu relé. No se envía nada hasta que toques Publicar.", "Publica uma nota pública no Nostr, assinada com a sua identidade Nostr ({k}), no seu relay. Nada é enviado até você tocar em Publicar.", "Veröffentlicht eine öffentliche Notiz auf Nostr, signiert mit Deiner Nostr-Identität ({k}), an Dein Relay. Nichts wird gesendet, bis Du auf Posten tippst.", "Publie une note publique sur Nostr, signée avec votre identité Nostr ({k}), sur votre relais. Rien n'est envoyé tant que vous n'appuyez pas sur Publier."),
("{n} relay", "{n} relé", "{n} relay", "{n} Relay", "{n} relais"),
("{n} relays", "{n} relés", "{n} relays", "{n} Relays", "{n} relais"),
("There is no Nostr key on this device yet, so posting is off. Copy the text and post it anywhere you like. Nothing is sent from here.", "Aún no hay una clave Nostr en este dispositivo, así que publicar está desactivado. Copia el texto y publícalo donde quieras. Desde aquí no se envía nada.", "Ainda não há uma chave Nostr neste dispositivo, então a publicação está desativada. Copie o texto e publique onde quiser. Nada é enviado daqui.", "Auf diesem Gerät gibt es noch keinen Nostr-Schlüssel, deshalb ist das Posten aus. Kopiere den Text und poste ihn, wo Du willst. Von hier wird nichts gesendet.", "Il n'y a pas encore de clé Nostr sur cet appareil, la publication est donc désactivée. Copiez le texte et publiez-le où vous voulez. Rien n'est envoyé d'ici."),
("Post", "Publicar", "Publicar", "Posten", "Publier"),
("Copy text", "Copiar texto", "Copiar texto", "Text kopieren", "Copier le texte"),
("POSTING…", "PUBLICANDO…", "PUBLICANDO…", "WIRD GEPOSTET…", "PUBLICATION…"),
("POSTED", "PUBLICADO", "PUBLICADO", "GEPOSTET", "PUBLIÉ"),
("Try again", "Reintentar", "Tentar de novo", "Nochmal versuchen", "Réessayer"),
("Posted to {n} relay.", "Publicado en {n} relé.", "Publicado em {n} relay.", "An {n} Relay gepostet.", "Publié sur {n} relais."),
("Posted to {n} relays.", "Publicado en {n} relés.", "Publicado em {n} relays.", "An {n} Relays gepostet.", "Publié sur {n} relais."),
("Couldn't reach any relay. You may be offline. Nothing was lost: your score is saved here. Try again, or copy the text.", "No se pudo contactar con ningún relé. Quizá no tengas conexión. No se perdió nada: tu puntuación está guardada aquí. Inténtalo de nuevo o copia el texto.", "Não foi possível alcançar nenhum relay. Você pode estar sem conexão. Nada foi perdido: sua pontuação está salva aqui. Tente de novo ou copie o texto.", "Kein Relay erreichbar. Vielleicht bist Du offline. Es ist nichts verloren: Dein Ergebnis ist hier gespeichert. Versuch es noch einmal oder kopiere den Text.", "Aucun relais n'a répondu. Vous êtes peut-être hors ligne. Rien n'est perdu" + NB + ": votre score est enregistré ici. Réessayez ou copiez le texte."),
("NUTCADE Daily Challenge {d}: {g} {s} 🕹️ #nutcade", "Reto diario de NUTCADE {d}: {g} {s} 🕹️ #nutcade", "Desafio diário do NUTCADE {d}: {g} {s} 🕹️ #nutcade", "NUTCADE Tages-Challenge {d}: {g} {s} 🕹️ #nutcade", "Défi du jour NUTCADE {d}" + NB + ": {g} {s} 🕹️ #nutcade"),
("FIRST RUN COUNTS", "LA 1ª PARTIDA CUENTA", "A 1ª PARTIDA CONTA", "ERSTER LAUF ZÄHLT", "LA 1RE PARTIE COMPTE"),
("PRACTICE RUN", "PARTIDA DE PRUEBA", "PARTIDA DE TREINO", "ÜBUNGSLAUF", "PARTIE D'ENTRAÎNEMENT"),
("CLOCK WRONG: NOT COUNTED", "RELOJ MAL: NO CUENTA", "RELÓGIO ERRADO: NÃO VALE", "UHR FALSCH: ZÄHLT NICHT", "HORLOGE FAUSSE: NON COMPTÉ"),
("A new daily challenge just started.", "Acaba de empezar un nuevo reto diario.", "Um novo desafio diário acabou de começar.", "Eine neue Tages-Challenge hat gerade begonnen.", "Un nouveau défi du jour vient de commencer."),
("OFFICIAL SCORE", "PUNTUACIÓN OFICIAL", "PONTUAÇÃO OFICIAL", "OFFIZIELLES ERGEBNIS", "SCORE OFFICIEL"),
("Your device clock looks wrong, so this run does not count as official.", "El reloj de tu dispositivo parece estar mal, así que esta partida no cuenta como oficial.", "O relógio do seu dispositivo parece estar errado, então esta partida não conta como oficial.", "Die Uhr Deines Geräts scheint falsch zu gehen, deshalb zählt dieser Lauf nicht als offiziell.", "L'horloge de votre appareil semble incorrecte : cette partie ne compte donc pas comme officielle."),
("Your official score today: {s}", "Tu puntuación oficial de hoy: {s}", "Sua pontuação oficial de hoje: {s}", "Dein offizielles Ergebnis heute: {s}", "Votre score officiel du jour" + NB + ": {s}"),
("Play again for fun", "Jugar otra vez por diversión", "Jogar de novo por diversão", "Zum Spaß nochmal spielen", "Rejouer pour le plaisir"),
("Exit", "Salir", "Sair", "Beenden", "Quitter"),
]
LANGS = ['es', 'pt', 'de', 'fr']
PH = re.compile(r'\{\w+\}')
if __name__ == '__main__':
    seen = set()
    for row in ROWS:
        assert len(row) == 5, row
        assert row[0] not in seen, row[0]; seen.add(row[0])
        for x in row[1:]: assert sorted(PH.findall(row[0])) == sorted(PH.findall(x)), row
    js = ['/* NUTCADE Daily Challenge translations, generated from i18n_daily.py: added to the dictionaries in i18n.js */', '(() => { const D = window.NUTCADE_I18N || {};', '  const add = (d, t) => { for (const k in t) if (!(k in d.t)) d.t[k] = t[k]; };']
    for i, l in enumerate(LANGS):
        js.append('  if (D.%s) add(D.%s, %s);' % (l, l, json.dumps({r[0]: r[i + 1] for r in ROWS}, ensure_ascii=False)))
    js.append('})();')
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'i18n_daily.js')
    open(out, 'w').write('\n'.join(js) + '\n')
    print('rows', len(ROWS))
