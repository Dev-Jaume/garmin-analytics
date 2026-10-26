# Mètodes de la versió Windows

## Friel clàssic running

Perfil requerit originalment, segons [l'article de Joe Friel a TrainingPeaks](https://www.trainingpeaks.com/learn/articles/joe-friel-s-quick-guide-to-setting-zones/):
percentatges de LTHR clàssics, no FC màxima. El [web actual de Friel](https://joefrieltraining.com/a-quick-guide-to-setting-zones/)
va revisar el mètode el 2025; es distingeixen explícitament els dos perfils.

Es demana LTHR validat, data i procedència, i es conserva cada versió. Per evitar buits
als BPM enters s'utilitzen límits inferiors ceil(LTHR×p), amb p=0.85, 0.90, 0.95, 1.00 i 1.03; Z5c comença a floor(1.06×LTHR)+1. El tram anterior arriba fins al BPM
immediatament inferior al següent tall. No es tracta d'arrodonir percentatges mostrats
independentment. Cada BPM enter té una sola zona; mostres decimals s'arrodoneixen
half-up només per classificar, sense modificar l'original.

Temps per zona: durada real entre timestamps, retenció de la lectura esquerra,
última mostra sense extrapolació. S'exclouen intervals <=0, buits superiors al límit
configurat, HR absent, flags temporals i pauses explícites (inclòs esdeveniment dins
l'interval). Un esdeveniment absent no prova continuïtat. No es descarta silenciosament
una mostra original ni es corregeix FC. Les quantitats excloses es mostren.

La qualitat òptica és descriptiva: disponibilitat de mostres, rang 30–240 BPM,
salts >25 BPM i coincidències amb cadència en unitat original. No és una probabilitat,
no detecta tots els errors ni prova cadence-lock. No inclou encara retard, deriva,
altiplans sostinguts ni càlcul retrospectiu de LTHR. La FC màxima no és LTHR.

## Daniels–Gilbert

Equacions de *Oxygen Power* (Daniels i Gilbert, 1979), reproduïdes en els [Eq. 7–9 de
recerca publicada](https://link.springer.com/content/pdf/10.1007/s11257-021-09299-3.pdf):

- v en m/min; t en minuts.
- cost(v) = −4.60 + 0.182258v + 0.000104v².
- f(t) = 0.8 + 0.1894393 exp(−0.012778t) + 0.2989558 exp(−0.1932605t).
- VDOT = cost(v)/f(t). No és VO₂max mesurat ni el VO₂max de Garmin.

Domini local conservador: 1500 m–marató, temps i puntuacions plausibles. Només
rendiments confirmats manualment, amb ID d'activitat, distància i temps total oficial.
El nivell actual és el resultat validat més recent de 90 dies, sense utilitzar proves
futures ni el màxim històric antic. Resultats fora d'aquesta finestra continuen a
l'històric, però no es declaren actuals. Equivalents de cursa per bisecció; no garanties
de rendiment ni correcció automàtica per meteorologia, terreny o GPS.

### Estimacions E/M/T/I/R (no taules oficials)

Derivació pròpia i transparent, només visible després d'activar una casella:

- E: invertir cost(v) a 59–74% del VDOT.
- I: invertir cost(v) a 97–100% del VDOT.
- M: ritme de la marató equivalent del model.
- T: ritme sostingut de 60 minuts segons f(60).
- R: interval entre els equivalents de 1500 m i una milla.

Les definicions E/I i R són a la [calculadora V.O2](https://vdoto2.com/calculator/);
T com a esforç proper a una hora és descrit per [Jack Daniels a V.O2](https://news.vdoto2.com/2022/09/a-different-perspective-quality-versus-quantity-in-your-training-plan/).
Apliquem aquestes descripcions al model de rendiment; no afirmem equivalència exacta
amb la metodologia interna ni les taules de la calculadora oficial. Les bandes
percentuals no transformen el VDOT en una mesura fisiològica de VO₂max.

Intervals: E/M continu; T només 1000/1200 m a la graella; I només quan tot el rang de
temps queda entre 3 i 5 minuts; R màxim local de 120 s. Són filtres prudents de la
interfície, no prescripcions ni regles oficials universals. Distàncies candidates:
200/300/400/600/800/1000/1200 m, mostrades només quan passen el filtre.

Els tests contrasten una referència de 5 km en 20 min (VDOT aproximat 49.806),
inversió i unitats, recència i filtres. Encara no hi ha regressió contra una taula
oficial V.O2 de ritmes: totes aquestes sortides continuen etiquetades com a estimacions.
