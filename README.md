<img src="assets/schienle-logo.png" alt="Schienle Magnettechnik" height=100>

# Schienle_PCB_Freigabe

KiCad-Plugin (KiCad 9/10) für die Leiterplatten-Freigabe: Zeichnungsnummer und Index eingeben, DRC prüfen, Fertigungsdaten, STEP, Schaltplan-PDF und Leiterplattenspezifikation erstellen und das Projekt zum Freigabezeitpunkt sichern.

Autor: Schienle. Basiert auf dem [Fabrication Toolkit](https://github.com/bennymeg/Fabrication-Toolkit) von Benny Megidish (Apache-2.0).

## Installation

KiCad → **Plugin and Content Manager** → **Install from File…** → ZIP auswählen. Danach erscheint das Schienle-Icon in der Werkzeugleiste des PCB-Editors.

Voraussetzung: KiCad 9 oder 10 (DRC, STEP, Schaltplan-PDF und Platinenansichten werden mit `kicad-cli` erzeugt).

## Ablauf einer Freigabe

1. Schaltplan speichern und die Platine aktualisieren (**F8**).
2. Im PCB-Editor auf das Schienle-Icon klicken, Zeichnungsnummer und Index prüfen, **Freigabe erstellen**.
3. Das Plugin
   - füllt die Zonen, schreibt den Index in das Platinen-Schriftfeld und **speichert die Platine**,
   - führt den **DRC** aus – **bei Fehlern wird keine Freigabe erstellt** (Warnungen und in KiCad ausgeschlossene Fehler blockieren nicht),
   - erzeugt den Freigabeordner und das Projekt-Backup.

```
<Projekt>/Freigaben/
└── <Zeichnungsnummer>_<Index>/
    ├── Gerberdaten/                              Gerber- und Bohrdaten (nicht gezippt)
    ├── <Name>_bom.csv                            Stückliste
    ├── <Name>_positions.csv                      Bestückungsliste
    ├── <Name>_designators.csv
    ├── <Name>_netlist.ipc                        IPC-Netzliste
    ├── <Name>.step                               3D-Modell
    ├── <Name>_Schaltplan.pdf                     alle Schaltplanblätter
    ├── <Name>_Leiterplattenspezifikation.pdf     Spezifikation (Seite 2: Ansicht Ober-/Unterseite)
    ├── <Name>_DRC-Bericht.txt                    DRC-Ergebnis (Warnungen)
    └── <Name>_Projekt-Backup.zip                 Projekt zum Freigabezeitpunkt

<Projekt>-backups/
    └── Freigabe_<Name>_<JJJJ-MM-TT_hhmmss>.zip   dasselbe Backup bei den automatischen KiCad-Backups
```

Die Kopie in `<Projekt>-backups/` zeigt die Freigabe-Historie neben den automatischen KiCad-Backups. Ihr Name folgt bewusst nicht dem KiCad-Backup-Muster, damit KiCads Aufräumen sie nie löscht. Eine bestehende Freigabe wird nur nach Rückfrage überschrieben.

## Zeichnungsnummer und Index

Empfohlen: **`ZEICHNUNGSNUMMER` und `INDEX` als Projekt-Textvariablen anlegen** (Datei → Board Setup bzw. Schaltplan-Setup → Text Variables) und in den Schriftfeldern von Schaltplan und Platine `${INDEX}` (und ggf. `${ZEICHNUNGSNUMMER}`) verwenden. Dann

- zeigen Schaltplan, Platine und alle PDFs immer denselben Stand,
- übernimmt das Plugin die Werte automatisch (Felder grau, nicht änderbar),
- bleibt eine Revision `${INDEX}` im Platinen-Schriftfeld erhalten (sie wird nicht durch den Wert ersetzt).

Ohne Projektvariablen werden Zeichnungsnummer und Index im Dialog eingegeben und pro Projekt gespeichert. Vor der Freigabe prüft das Plugin, ob die Revision im (gespeicherten) Schaltplan-Schriftfeld zum Index passt, und fragt bei Abweichung nach.

## Optionen (Reiter „Freigabe“)

☑ __Index in die Revision des Platinen-Schriftfelds schreiben__ (außer die Revision verweist auf eine Textvariable)</br>
☑ __Alle Zonen vor der Freigabe füllen__</br>
☑ __3D-Modell exportieren (STEP)__</br>
☑ __Schaltplan als PDF exportieren__: alle Blätter von `<Projekt>.kicad_sch`; `${ZEICHNUNGSNUMMER}` und `${INDEX}` stehen im Schaltplan zur Verfügung.</br>
☑ __Leiterplattenspezifikation erstellen (PDF)__, optional __mit Ansicht Ober- und Unterseite__ (3D-Rendering mit Bauteilmodellen)</br>
☑ __Projekt-Backup erstellen__: Schaltplan, Platine, Bibliotheken, 3D-Modelle usw.; `Freigaben/`, Backups, Lock-Dateien, `fp-info-cache` und VCS-Ordner werden ausgelassen.</br>
☑ __Freigabeordner danach öffnen__</br>

Unter **Erweitert (Fertigungsdaten)** liegen die Optionen des Original-Toolkits: zusätzliche Lagen, alle aktiven Lagen plotten, User.1 als V-Cut-Lage, User.2 als alternative Kontur, JLC-Bestückungskorrekturen und DNP-Bauteile aus der Stückliste ausschließen.

Alle Einstellungen werden pro Projekt in `fabrication-toolkit-options.json` gespeichert.

## Leiterplattenspezifikation (Reiter „Leiterplattenspezifikation“)

Kopf (Projekt, Firma, Freigegeben von), Allgemein, Leiterplatte, Mechanische Bearbeitung und Bemerkungen. Grau hinterlegte Werte werden nicht im Dialog gepflegt, sondern kommen aus KiCad:

| Wert | Quelle |
|---|---|
| Lagenanzahl, Abmessungen | Platine |
| Leiterplattendicke | Platine (änderbar) |
| Basismaterial, Kupferdicke (außen/innen), Oberfläche, Lötstopplack- und Bestückungsdruckfarbe | **Board Setup → Physical Stackup**, sofern dort definiert |

Alle übrigen Werte (z. B. Materialtyp, Via-Füllung, Konturbearbeitung, Bemerkungen) werden pro Projekt gespeichert.

## Fehlersuche

Jeder Lauf wird mit Zeitstempel und Dauer pro Schritt in `schienle-pcb-freigabe.log` im Projektordner protokolliert (inkl. KiCad-Version, Optionen, `kicad-cli`-Aufrufen und -Ausgaben sowie vollständigen Fehlermeldungen). Der aktuelle Schritt steht während der Freigabe auch im Fenstertitel.

## Bauteil-Attribute (Erweitert, aus dem Original-Toolkit)

Die folgenden Attribute stammen aus dem Fabrication Toolkit (englische Originaldokumentation). Sie steuern MPN, Rotations- und Positionskorrekturen für die Bestückungsliste – relevant vor allem in Verbindung mit „JLC-Bestückungskorrekturen anwenden“.


> [!NOTE]  
> All the attributes are entered in the Schematic Editor, make sure to update your PCB [**F8**] with the changes made to the schematic before generating a new set of production files, otherwise your changes won't be reflected.

### ① Include Component Part Number in Production Files
Add an 'LCSC Part #'* field with the LCSC component part number to the symbol's fields property.

<img src="https://github.com/bennymeg/JLC-Plugin-for-KiCad/blob/master/assets/mpn.png?raw=true" height=420>

#### Primary Fields*:
| 'LCSC Part #' | 'LCSC Part' | 'LCSC PN' | 'LCSC P/N' | 'LCSC Part No.' | 'LCSC Part Number' | 'JLCPCB Part #' | 'JLCPCB Part' | 'JLCPCB PN' | 'JLCPCB P/N' | 'JLCPCB Part No.' | 'JLCPCB Part Number' |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

_The fields will be queried in the order denoted above._

#### Fallback Fields*:
| 'LCSC' | 'JLC' | 'MPN' | 'Mpn' | 'mpn' |
| --- | --- | --- | --- | --- |

_The fields will be queried in the order denoted above._

Empty fields are skipped so, for example, a 'MPN' field with a value will be used if
all earlier fields are missing or empty.

---

### ② Ignore Footprint in Production Files
Select 'Exclude from board' or 'Exclude from BOM' in the symbol's attributes property in order to ignore the footprint from the relevant file.

<img src="https://github.com/bennymeg/JLC-Plugin-for-KiCad/blob/master/assets/attributes.png?raw=true" height=420>

Select 'Exclude from position files' or 'Exclude from BOM' in the footprint's fabrication attributes property in order to ignore the footprint from the relevant file.

<img src="https://github.com/bennymeg/JLC-Plugin-for-KiCad/blob/master/assets/fabrication.png?raw=true" height=505>

---

### ③ Offset Component Rotation
The rotation of components in KiCad Footprints does not always match the orientation in the JLC library because KiCad and JLC PCB used different variation of the same standard. Most of the rotations may be corrected by the `rotations.cf` definitions. To the exception cases: add an 'FT Rotation Offset'* field - with positive values indicating counter-clockwise orientation offset in degrees.

<img src="https://github.com/bennymeg/JLC-Plugin-for-KiCad/blob/master/assets/rotation-jlc.png?raw=true" height=164>

If the JLC preview shows a footprint like this, enter a rotation offset of -90 to rotate pin 1 to the lower right corner.

<img src="https://github.com/bennymeg/JLC-Plugin-for-KiCad/blob/master/assets/rotation.png?raw=true" height=420>

Use following table to quickly find out to which coordinate enter the correction based on JLC arrows clicks - depending on footprint rotation in KiCad PCB Editor status bar:
|KiCad footprint deg | x | y|
|----|----|----|
|0 deg, Front | right arrow | up arrow |
|0 deg, Back | left arrow | down arrow |
|180 deg, Front | left arrow | down arrow |
|180 deg, Back | right arrow | up arrow |
|90 deg, Front or Back | up arrow | left arrow |
|-90 deg, Front or Back | down arrow | right arrow |

> [!TIP]  
> Single arrow press in JLC is 0.0635mm (= 1/400in) shift.

#### Primary Fields*:
| 'FT Rotation Offset' |
| --- |

_The fields will be queried in the order denoted above._

#### Fallback Fields*:
| 'Rotation Offset' | 'RotOffset' |
| --- | --- |

_The fields will be queried in the order denoted above._

---

### ④ Offset Component Position
The position of components in KiCad Footprints does not always match the orientation in the JLC library because KiCad and JLCPCB used different variation of the same standard. To the exception cases: add an 'FT Position Offset'* field with an comma separated x,y position offset to correct it.

<img src="https://github.com/bennymeg/JLC-Plugin-for-KiCad/blob/master/assets/position.png?raw=true" height=420>

> [!TIP]  
> Single arrow press in JLC equals to 0.0635mm (= 1/400in) shift.

#### Primary Fields*:
| 'FT Position Offset' |
| --- |

_The fields will be queried in the order denoted above._

#### Fallback Fields*:
| 'Position Offset' | 'PosOffset' |
| --- | --- |

_The fields will be queried in the order denoted above._

### ⑤ Override Component Origin
The Fabrication Toolkit reports the position of each component based on an automatically selected point of reference. This default behavior can be overridden by adding an 'FT Origin'* field to the component.

#### Primary Fields*:
| 'FT Origin' |
| --- |

_The fields will be queried in the order denoted above._

#### Fallback Fields*:
| 'Origin' |
| --- |

The **Origin** field supports the following values:

- `Anchor` - Uses the footprint's anchor point, which can be modified in KiCad's footprint editor.
- `Center` - Uses the center of the bounding box formed by the footprint's pads.

### ⑥ Override Component Layer
Some footprints may have their components defined on the opposite layer to there actual footprints. In these instances you can override mount side by adding an 'FT Layer Override'* field to the component.

The **Layer Override** field supports the following values:
- `top`, `t` - Override footprint layer to the top.
- `bottom`, `b` - Override footprint layer to the bottom.

#### Primary Fields*:
| 'FT Layer Override' |
| --- |

_The fields will be queried in the order denoted above._

#### Fallback Fields*:
| 'Layer Override' | 'LayerOverride' |
| --- | --- |

_The fields will be queried in the order denoted above._


## Kommandozeile

Die Freigabe (ohne Leiterplattenspezifikation) lässt sich auch ohne Oberfläche erstellen, z. B. für Automatisierung:

```
python3 -m plugins.cli -p /meinProjekt/meinePlatine.kicad_pcb -dn 4711-02 -i B -sR -f -st -sp -pB -nI
```

```
python3 -m plugins.cli -h

usage: Schienle_PCB_Freigabe [-h] --path PATH --drawingNumber NUMMER --index INDEX [--setRevision] [--autoFill]
                             [--stepExport] [--schematicPdf] [--projectBackup] [--overwrite] [--openBrowser]
                             [--nonInteractive] [--additionalLayers LAGEN] [--allActiveLayers] [--user1VCut]
                             [--user2AltVCut] [--autoTranslate] [--excludeDNP]

  --path, -p PATH       Pfad zur KiCad-Platine (.kicad_pcb)
  --drawingNumber, -dn NUMMER
                        Zeichnungsnummer der Freigabe
  --index, -i INDEX     Index der Freigabe (z. B. A, B, 01)
  --setRevision, -sR    Index in die Revision des Platinen-Schriftfelds schreiben
  --autoFill, -f        Alle Zonen vor der Freigabe füllen
  --stepExport, -st     3D-Modell als STEP exportieren
  --schematicPdf, -sp   Schaltplan als PDF exportieren
  --projectBackup, -pB  Projekt-Backup erstellen
  --overwrite, -o       Bestehende Freigabe überschreiben
  --openBrowser, -b     Freigabeordner danach öffnen
  --nonInteractive, -nI Ohne Fortschrittsanzeige (z. B. für CI)
  --additionalLayers, -aL LAGEN, --allActiveLayers, -aaL, --user1VCut, -u1, --user2AltVCut, -u2,
  --autoTranslate, -t, --excludeDNP, -e
                        Erweiterte Optionen wie im Dialog
```

Unter Windows in der `KiCad Command Prompt` mit `python` statt `python3` ausführen. Für das installierte Plugin `plugins.cli` durch den Paketnamen ersetzen, z. B.
`python -m "${KICAD10_3RD_PARTY}plugins/com_schienle_Schienle-PCB-Freigabe.cli" -p "${KIPRJMOD}/${PROJECTNAME}.kicad_pcb" -dn 4711-02 -i B`

## Autor

Schienle

Original Fabrication Toolkit: Benny Megidish (Apache-2.0)
