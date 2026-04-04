import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    clip: true
    contentWidth: availableWidth
    background: Rectangle { color: theme.bg }

    readonly property color bg:      theme.bg
    readonly property color surface: theme.surface
    readonly property color accent:  theme.accent
    readonly property color text_:   theme.fg
    readonly property color dim:     theme.dim
    readonly property color border_: theme.outline

    // ── Full pool of 50 inspiration prompts ─────────────────────────────
    readonly property var allPrompts: [
        // ── Vocal prompts ────────────────────────────────────────────────────
        "R&B ballad with female vocalist",       "Pop anthem with male singer",
        "Soulful gospel with lead vocals",        "Indie folk song with soft female voice",
        "Hip-hop verse with male rapper",         "Country heartbreak with female singer",
        "Dreamy pop with airy female vocals",     "Emotional piano ballad with male singer",
        "Jazz standard with female vocalist",     "Dark R&B with breathy female voice",
        "Upbeat funk with male lead vocals",      "Bittersweet indie pop with vocals",
        "Latin pop with female singer",           "90s neo-soul with warm female voice",
        "Alt-rock with raw male vocals",          "Soft acoustic love song female vocals",
        "Reggae with mellow male vocalist",       "Electronic pop with female vocals",
        "Blues singer with gritty male voice",    "Anthemic rock with soaring vocals",
        // ── Instrumental prompts ─────────────────────────────────────────────
        "Upbeat lo-fi hip hop",                   "Dark orchestral trailer",
        "Melancholic indie folk ballad",           "Aggressive trap 808 bass",
        "Dreamy synthwave neon nights",            "Epic cinematic battle score",
        "Chill jazz café afternoon",               "Deep house midnight groove",
        "Acoustic fingerpicking campfire",         "Haunting ambient drone textures",
        "Euphoric big-room EDM drop",              "Slow burn blues guitar",
        "Retro 80s synth pop",                     "Punchy boom bap hip hop",
        "Lush neoclassical piano strings",         "Driving post-rock crescendo",
        "Soulful R&B late night",                  "Minimal techno warehouse rave",
        "Nordic folk fiddle dance",                "Orchestral horror suspense",
        "Warm vinyl lo-fi study",                  "Reggaeton tropical bounce",
        "Progressive metal riff breakdown",        "Bittersweet acoustic singer-songwriter",
        "Future bass emotional drop",              "Ethereal choral ambient",
        "Funky 70s soul groove",                   "Dark trap emotional rage",
        "Jazz fusion electric guitar",             "Peaceful meditation flute",
        "Uplifting gospel choir",                  "Cyberpunk industrial glitch",
        "Afrobeats percussive party",              "Nostalgic lo-fi childhood",
        "Triumphant film score strings",           "Psychedelic surf rock reverb",
        "Smooth bossa nova guitar",                "Brutal death metal blast",
        "Gentle lullaby music box",                "Energetic punk rock riot",
        "Tropical deep house sunset",              "Melancholic cello solo",
        "Retro video game chiptune",               "Dark moody trip-hop",
        "Bluegrass banjo hoedown",                 "Sparkling bedroom pop",
        "Dramatic flamenco guitar",                "Arctic ambient frozen tundra",
        "Groovy disco funk bassline",              "Soaring power ballad anthem",
        // ── NCS / Future Bass prompts ────────────────────────────────────────
        "NCS future bass emotional drop",          "Melodic dubstep supersaw anthem",
        "Big room festival EDM crowd",             "NCS pluck lead over 808 bass",
        "Uplifting vocal chop future bass",        "Dark melodic dubstep breakdown",
        "Euphoric NCS anthem drop 128bpm",         "Supersaw chord stack future bass"
    ]

    property var shownPrompts: []

    function pickSix() {
        var pool = allPrompts.slice()
        for (var i = pool.length - 1; i > 0; i--) {
            var j = Math.floor(Math.random() * (i + 1))
            var tmp = pool[i]; pool[i] = pool[j]; pool[j] = tmp
        }
        shownPrompts = pool.slice(0, 6)
    }

    Component.onCompleted: pickSix()

    // ── Singer warning state ─────────────────────────────────────────────
    property bool   singerWarnVisible: false
    property string singerWarnMsg:     ""
    property var    singerPendingOpts: ({})

    Connections {
        target: backend
        function onSingerWarning(message, pendingOpts) {
            root.singerWarnMsg     = message
            root.singerPendingOpts = pendingOpts
            root.singerWarnVisible = true
        }
    }

    Connections {
        target: backend
        function onStemsExtracted(stems) {
            soundsTab.stems = stems
        }
    }

    ColumnLayout {
        width: root.availableWidth - 4
        x: 4
        spacing: 10

        // ── Singer warning banner ─────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.leftMargin: 16; Layout.rightMargin: 16
            Layout.preferredHeight: visible ? warnCol.implicitHeight + 16 : 0
            visible: root.singerWarnVisible
            color: Qt.rgba(1, 0.85, 0.2, 0.12)
            border.color: Qt.rgba(1, 0.85, 0.2, 0.5)
            border.width: 1
            radius: 8

            ColumnLayout {
                id: warnCol
                anchors { left: parent.left; right: parent.right; top: parent.top }
                anchors.margins: 10
                spacing: 8

                RowLayout {
                    spacing: 6
                    Text { text: "\u26A0"; color: "#ffd600"; font.pixelSize: 13 }
                    Text {
                        Layout.fillWidth: true
                        text: root.singerWarnMsg
                        color: theme.fg; font.pixelSize: 11
                        wrapMode: Text.Wrap
                    }
                    Text {
                        text: "\u2715"; color: "#ffd600"; font.pixelSize: 13
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.singerWarnVisible = false
                        }
                    }
                }

                // Generate Anyway button
                Rectangle {
                    Layout.alignment: Qt.AlignRight
                    implicitWidth: anywaLabel.implicitWidth + 20
                    implicitHeight: 26; radius: 6
                    color: Qt.rgba(1, 0.85, 0.2, 0.18)
                    border.color: Qt.rgba(1, 0.85, 0.2, 0.6); border.width: 1
                    Text {
                        id: anywaLabel
                        anchors.centerIn: parent
                        text: "Generate Anyway"
                        color: "#ffd600"; font.pixelSize: 11; font.bold: true
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.singerWarnVisible = false
                            var confirmedOpts = Object.assign({}, root.singerPendingOpts)
                            confirmedOpts.singer_confirmed = true
                            backend.generate(confirmedOpts.prompt || "", confirmedOpts)
                        }
                    }
                }
            }
        }

        // ── Sub-tab pill bar ─────────────────────────────────────────
        PillTabBar {
            id: genPillBar
            Layout.fillWidth: true
            Layout.topMargin: 12
            Layout.leftMargin: 16
            Layout.rightMargin: 16
            model: ["Simple", "Advanced", "Sounds"]
            currentIndex: 0
            accentColor: accent
            onTabChanged: function(idx) {
                subStack.currentIndex = idx
                if (idx === 2) soundsTab.refreshSongTracks()
            }
        }

        StackLayout {
            id: subStack
            Layout.fillWidth: true
            Layout.leftMargin: 16
            Layout.rightMargin: 16
            Layout.preferredHeight: currentIndex === 0 ? children[0].implicitHeight
                                  : currentIndex === 1 ? children[1].implicitHeight
                                  : children[2].implicitHeight
            currentIndex: 0

            // ── Simple page ──────────────────────────────────────────
            ColumnLayout {
                spacing: 14

                // Prompt box — GlassCard with focus glow
                GlassCard {
                    Layout.fillWidth: true
                    title: "Describe your music"
                    accentColor: accent
                    focusItem: promptArea

                    TextArea {
                        id: promptArea
                        Layout.fillWidth: true
                        Layout.minimumHeight: 56
                        color: text_
                        font.pixelSize: 13
                        wrapMode: TextEdit.Wrap
                        background: null
                    }
                }

                // Inspiration chips header + regenerate
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    SectionLabel { text: "Inspiration"; accentColor: accent }
                    Item { Layout.fillWidth: true }
                    Rectangle {
                        width: 88; height: 24; radius: 12
                        color: regenMouse.containsMouse ? Qt.lighter(surface, 1.4) : surface
                        border.color: border_
                        Text {
                            anchors.centerIn: parent
                            text: "\u21BB  Shuffle"
                            color: dim
                            font.pixelSize: 10
                        }
                        MouseArea {
                            id: regenMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.pickSix()
                        }
                    }
                }

                // Pill-shaped inspiration chips
                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 6
                    rowSpacing: 6

                    Repeater {
                        model: root.shownPrompts
                        delegate: Rectangle {
                            required property string modelData
                            Layout.fillWidth: true
                            implicitHeight: 28
                            radius: 14
                            color: chipMouse.containsMouse
                                   ? Qt.rgba(accent.r, accent.g, accent.b, 0.18)
                                   : Qt.rgba(surface.r, surface.g, surface.b, 0.7)
                            border.color: chipMouse.containsMouse
                                          ? Qt.rgba(accent.r, accent.g, accent.b, 0.55)
                                          : border_
                            Behavior on border.color { ColorAnimation { duration: 120 } }

                            Text {
                                anchors.centerIn: parent
                                text: modelData
                                color: text_
                                font.pixelSize: 11
                                elide: Text.ElideRight
                                width: parent.width - 16
                                horizontalAlignment: Text.AlignHCenter
                            }
                            MouseArea {
                                id: chipMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: promptArea.text = modelData
                            }
                        }
                    }
                }

                // Duration + Lyrics
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Text { text: "Duration:"; color: dim; font.pixelSize: 11 }
                    ComboBox {
                        id: simpleTimeCombo
                        model: ["(auto)", "15 s", "30 s", "60 s", "90 s", "120 s", "180 s"]
                        Layout.fillWidth: true
                    }
                    Text { text: "Lyrics:"; color: dim; font.pixelSize: 11 }
                    ComboBox {
                        id: simpleLyricsCombo
                        model: ["Auto", "Custom", "Instrumental"]
                        Layout.fillWidth: true
                    }
                }

                // Custom lyrics text (Simple tab)
                GlassCard {
                    Layout.fillWidth: true
                    title: "Custom Lyrics"
                    accentColor: accent
                    visible: simpleLyricsCombo.currentText === "Custom"

                    // Section tag buttons
                    Flow {
                        Layout.fillWidth: true
                        spacing: 4
                        Repeater {
                            model: ["[Intro]", "[Verse]", "[Chorus]", "[Bridge]", "[Outro]"]
                            delegate: Rectangle {
                                required property string modelData
                                width: tagLbl.implicitWidth + 12; height: 22; radius: 11
                                color: tagMa.containsMouse
                                       ? Qt.rgba(accent.r, accent.g, accent.b, 0.18)
                                       : Qt.rgba(surface.r, surface.g, surface.b, 0.7)
                                border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.4)
                                Text {
                                    id: tagLbl; anchors.centerIn: parent
                                    text: modelData; color: accent; font.pixelSize: 10
                                }
                                MouseArea {
                                    id: tagMa; anchors.fill: parent; hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: simpleLyricsArea.insert(simpleLyricsArea.cursorPosition, modelData + "\n")
                                }
                            }
                        }
                    }

                    TextArea {
                        id: simpleLyricsArea
                        Layout.fillWidth: true
                        Layout.minimumHeight: 80
                        placeholderText: "Type or paste lyrics here...\nUse [Verse], [Chorus] etc. for sections"
                        color: text_
                        font.pixelSize: 13
                        wrapMode: TextEdit.Wrap
                        background: null
                    }
                }

                // ── Recent Generations ────────────────────────────────
                SectionLabel {
                    text: "Recent \u00B7 " + backend.generations.count
                    accentColor: accent
                    visible: backend.generations.count > 0
                }

                Repeater {
                    model: backend.generations
                    delegate: Rectangle {
                        required property string prompt
                        required property string audioPath
                        required property double duration
                        required property int    index

                        Layout.fillWidth: true
                        height: 60
                        radius: 8
                        color: genRowMa.containsMouse
                               ? Qt.rgba(accent.r, accent.g, accent.b, 0.10)
                               : Qt.rgba(surface.r, surface.g, surface.b, 0.85)
                        border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.25)
                        border.width: 1
                        Behavior on color { ColorAnimation { duration: 80 } }

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 8

                            // Waveform + prompt
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 3
                                Text {
                                    text: prompt
                                    color: text_; font.pixelSize: 11
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Row {
                                    spacing: 2
                                    Repeater {
                                        model: 22
                                        Rectangle {
                                            required property int index
                                            width: 3
                                            height: Math.max(3, (index % 6 + 1) * 2 + (index % 4) * 1)
                                            radius: 1
                                            color: Qt.rgba(accent.r, accent.g, accent.b, 0.45)
                                            anchors.bottom: parent ? parent.bottom : undefined
                                        }
                                    }
                                }
                            }

                            // Duration
                            Text {
                                text: duration.toFixed(1) + "s"
                                color: dim; font.pixelSize: 10
                                Layout.alignment: Qt.AlignVCenter
                            }

                            // Play button
                            Rectangle {
                                width: 28; height: 28; radius: 14
                                color: playMa.containsMouse
                                       ? Qt.rgba(accent.r, accent.g, accent.b, 0.30)
                                       : Qt.rgba(accent.r, accent.g, accent.b, 0.14)
                                border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.5)
                                border.width: 1
                                Behavior on color { ColorAnimation { duration: 80 } }
                                Text {
                                    anchors.centerIn: parent
                                    text: "\u25B6"
                                    color: accent; font.pixelSize: 10
                                }
                                MouseArea {
                                    id: playMa
                                    anchors.fill: parent; hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.previewAudio(audioPath)
                                }
                            }

                            // Insert button
                            Rectangle {
                                width: 54; height: 28; radius: 14
                                color: insMa.containsMouse ? accent
                                       : Qt.rgba(accent.r, accent.g, accent.b, 0.18)
                                border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.65)
                                border.width: 1
                                Behavior on color { ColorAnimation { duration: 80 } }
                                Text {
                                    anchors.centerIn: parent
                                    text: "\u2190 Insert"
                                    color: insMa.containsMouse ? "#fff" : accent
                                    font.pixelSize: 10; font.weight: Font.SemiBold
                                }
                                MouseArea {
                                    id: insMa
                                    anchors.fill: parent; hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.insertGeneration(index)
                                }
                            }
                        }

                        MouseArea {
                            id: genRowMa
                            anchors.fill: parent; hoverEnabled: true
                            propagateComposedEvents: true
                            onClicked: mouse.accepted = false
                        }
                    }
                }
            }

            // ── Advanced page ────────────────────────────────────────
            ColumnLayout {
                spacing: 8

                GlassCard {
                    Layout.fillWidth: true
                    title: "Generation Settings"
                    accentColor: accent

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: 8
                        rowSpacing: 6

                        Text { text: "Model:"; color: dim; font.pixelSize: 11 }
                        ComboBox {
                            id: modelCombo
                            Layout.fillWidth: true
                            model: backend.modelNames
                        }

                        Text { text: "Genre:"; color: dim; font.pixelSize: 11 }
                        ComboBox {
                            id: genreCombo
                            Layout.fillWidth: true
                            model: ["(auto)","Lo-Fi","Pop","Rock","Jazz","Electronic",
                                    "Classical","Hip-Hop","Ambient","Metal","R&B"]
                        }

                        Text { text: "Key:"; color: dim; font.pixelSize: 11 }
                        ComboBox {
                            id: keyCombo
                            Layout.fillWidth: true
                            model: ["(auto)","C major","G major","D major","A major",
                                    "E major","B major","F# major","C minor","G minor",
                                    "D minor","A minor","E minor"]
                        }

                        Text { text: "Tempo:"; color: dim; font.pixelSize: 11 }
                        ComboBox {
                            id: tempoCombo
                            Layout.fillWidth: true
                            model: ["(auto)","80 BPM","100 BPM","120 BPM","140 BPM","160 BPM","180 BPM"]
                        }

                        Text { text: "Duration:"; color: dim; font.pixelSize: 11 }
                        ComboBox {
                            id: durationCombo
                            Layout.fillWidth: true
                            model: ["(auto)","15 s","30 s","60 s","90 s","120 s","180 s","240 s"]
                        }

                        Text { text: "Lyrics:"; color: dim; font.pixelSize: 11 }
                        ComboBox {
                            id: lyricsCombo
                            Layout.fillWidth: true
                            model: ["Auto", "Custom", "Instrumental"]
                        }

                        // Section tag buttons (spans both columns, Advanced tab)
                        Flow {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            visible: lyricsCombo.currentText === "Custom"
                            spacing: 4
                            Repeater {
                                model: ["[Intro]", "[Verse]", "[Chorus]", "[Bridge]", "[Outro]"]
                                delegate: Rectangle {
                                    required property string modelData
                                    width: advTagLbl.implicitWidth + 12; height: 22; radius: 11
                                    color: advTagMa.containsMouse
                                           ? Qt.rgba(accent.r, accent.g, accent.b, 0.18)
                                           : Qt.rgba(surface.r, surface.g, surface.b, 0.7)
                                    border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.4)
                                    Text {
                                        id: advTagLbl; anchors.centerIn: parent
                                        text: modelData; color: accent; font.pixelSize: 10
                                    }
                                    MouseArea {
                                        id: advTagMa; anchors.fill: parent; hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: lyricsArea.insert(lyricsArea.cursorPosition, modelData + "\n")
                                    }
                                }
                            }
                        }

                        // Custom lyrics text (spans both columns, Advanced tab)
                        Rectangle {
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            visible: lyricsCombo.currentText === "Custom"
                            height: visible ? 90 : 0
                            color: Qt.rgba(theme.surface.r, theme.surface.g, theme.surface.b, 0.5)
                            radius: 6
                            border.color: border_

                            TextArea {
                                id: lyricsArea
                                anchors.fill: parent
                                anchors.margins: 4
                                placeholderText: "Type or paste lyrics here...\nUse [Verse], [Chorus] etc. for sections"
                                color: text_
                                font.pixelSize: 12
                                wrapMode: TextEdit.Wrap
                                background: null
                            }
                        }

                        Text { text: "Stems:"; color: dim; font.pixelSize: 11 }
                        ComboBox {
                            id: stemsCombo
                            Layout.fillWidth: true
                            model: ["Off","2 stems","4 stems","6 stems (Studio)"]
                        }
                    }

                    CheckBox {
                        id: sectionChk
                        text: "Section structure (Intro, Verse, Chorus)"
                        checked: true
                        palette.windowText: text_
                    }
                }
            }

            // ── Sounds page ──────────────────────────────────────────
            ColumnLayout {
                id: soundsTab
                property string extractPath: ""
                property string extractMode: "auto"
                property var    stems: []
                property var    songTracks: []
                spacing: 10

                function refreshSongTracks() {
                    soundsTab.songTracks = backend.getSongAudioTracks()
                }

                // ── Extract Stems card ────────────────────────────────
                GlassCard {
                    Layout.fillWidth: true
                    title: "Extract Stems"
                    accentColor: accent

                    // Mode toggle
                    PillTabBar {
                        id: extractModePill
                        Layout.fillWidth: true
                        model: ["Auto detect", "Vocal + Instrumental"]
                        accentColor: accent
                        onTabChanged: function(idx) {
                            soundsTab.extractMode = idx === 0 ? "auto" : "2stem"
                        }
                    }

                    // ── Browse file ───────────────────────────────────
                    SectionLabel { text: "From file"; accentColor: accent }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Text {
                            text: soundsTab.extractPath.length > 0
                                  ? soundsTab.extractPath
                                  : "No file selected"
                            color: soundsTab.extractPath.length > 0 ? theme.fg : theme.dim
                            font.pixelSize: 11
                            Layout.fillWidth: true
                            elide: Text.ElideMiddle
                        }
                        Button {
                            text: "Browse..."
                            onClicked: {
                                var p = backend.browseAudioFile()
                                if (p.length > 0) soundsTab.extractPath = p
                            }
                        }
                    }

                    // ── From generated tracks ─────────────────────────
                    SectionLabel {
                        text: "From generated tracks"
                        accentColor: accent
                        visible: backend.generations.count > 0
                    }

                    Repeater {
                        model: backend.generations
                        delegate: Rectangle {
                            required property string prompt
                            required property string audioPath
                            required property double duration
                            required property int    index

                            Layout.fillWidth: true
                            height: 56
                            radius: 6
                            color: genPickMa.containsMouse
                                   ? Qt.rgba(accent.r, accent.g, accent.b, 0.12)
                                   : surface
                            border.color: soundsTab.extractPath === audioPath
                                          ? Qt.rgba(accent.r, accent.g, accent.b, 0.85)
                                          : border_
                            border.width: soundsTab.extractPath === audioPath ? 2 : 1
                            Behavior on color       { ColorAnimation { duration: 80 } }
                            Behavior on border.color { ColorAnimation { duration: 80 } }

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 8

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    Text {
                                        text: prompt
                                        color: text_; font.pixelSize: 11
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                    Row {
                                        spacing: 2
                                        Repeater {
                                            model: 20
                                            Rectangle {
                                                required property int index
                                                width: 3
                                                height: Math.max(3, (index % 5 + 1) * 3 + (index % 3) * 2)
                                                radius: 1
                                                color: Qt.rgba(accent.r, accent.g, accent.b,
                                                               soundsTab.extractPath === audioPath ? 0.65 : 0.35)
                                                anchors.bottom: parent ? parent.bottom : undefined
                                            }
                                        }
                                    }
                                }

                                Text {
                                    text: duration.toFixed(1) + " s"
                                    color: dim; font.pixelSize: 10
                                }

                                Rectangle {
                                    width: 52; height: 24; radius: 12
                                    color: soundsTab.extractPath === audioPath
                                           ? accent
                                           : (usePickMa.containsMouse
                                              ? Qt.rgba(accent.r, accent.g, accent.b, 0.30)
                                              : Qt.rgba(accent.r, accent.g, accent.b, 0.12))
                                    border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.6)
                                    border.width: 1
                                    Behavior on color { ColorAnimation { duration: 80 } }
                                    Text {
                                        anchors.centerIn: parent
                                        text: soundsTab.extractPath === audioPath
                                              ? "\u2713 Set" : "Use"
                                        color: soundsTab.extractPath === audioPath ? "#fff" : accent
                                        font.pixelSize: 10; font.weight: Font.SemiBold
                                    }
                                    MouseArea {
                                        id: usePickMa
                                        anchors.fill: parent; hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: soundsTab.extractPath = audioPath
                                    }
                                }
                            }

                            MouseArea {
                                id: genPickMa
                                anchors.fill: parent; hoverEnabled: true
                                propagateComposedEvents: true
                                onClicked: { soundsTab.extractPath = audioPath; mouse.accepted = false }
                            }
                        }
                    }

                    // ── From Song Editor tracks ───────────────────────
                    SectionLabel {
                        text: "From Song Editor tracks"
                        accentColor: accent
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: soundsTab.songTracks.length === 0
                                  ? "No audio tracks loaded"
                                  : soundsTab.songTracks.length + " track" + (soundsTab.songTracks.length === 1 ? "" : "s") + " found"
                            color: dim; font.pixelSize: 10
                            Layout.fillWidth: true
                        }
                        Rectangle {
                            implicitWidth: refreshSongLbl.implicitWidth + 14
                            implicitHeight: 22
                            radius: 4
                            color: Qt.rgba(theme.fg.r, theme.fg.g, theme.fg.b, 0.05)
                            border.color: border_; border.width: 1
                            Text {
                                id: refreshSongLbl
                                text: "\u21BB Refresh"
                                color: dim; font.pixelSize: 10
                                anchors.centerIn: parent
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: soundsTab.refreshSongTracks()
                            }
                        }
                    }

                    Repeater {
                        model: soundsTab.songTracks
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            height: 44
                            radius: 6
                            color: songPickMa.containsMouse
                                   ? Qt.rgba(accent.r, accent.g, accent.b, 0.12)
                                   : surface
                            border.color: soundsTab.extractPath === modelData.path
                                          ? Qt.rgba(accent.r, accent.g, accent.b, 0.85)
                                          : border_
                            border.width: soundsTab.extractPath === modelData.path ? 2 : 1
                            Behavior on color        { ColorAnimation { duration: 80 } }
                            Behavior on border.color { ColorAnimation { duration: 80 } }

                            RowLayout {
                                anchors.fill: parent; anchors.margins: 8; spacing: 8
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 2
                                    Text {
                                        text: modelData.name
                                        color: text_; font.pixelSize: 11
                                        elide: Text.ElideRight; Layout.fillWidth: true
                                    }
                                    Text {
                                        text: modelData.path.split("/").pop().split("\\").pop()
                                        color: dim; font.pixelSize: 9
                                        elide: Text.ElideRight; Layout.fillWidth: true
                                    }
                                }
                                Rectangle {
                                    width: 52; height: 24; radius: 12
                                    color: soundsTab.extractPath === modelData.path
                                           ? accent
                                           : (songUseMa.containsMouse
                                              ? Qt.rgba(accent.r, accent.g, accent.b, 0.30)
                                              : Qt.rgba(accent.r, accent.g, accent.b, 0.12))
                                    border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.6)
                                    border.width: 1
                                    Behavior on color { ColorAnimation { duration: 80 } }
                                    Text {
                                        anchors.centerIn: parent
                                        text: soundsTab.extractPath === modelData.path ? "\u2713 Set" : "Use"
                                        color: soundsTab.extractPath === modelData.path ? "#fff" : accent
                                        font.pixelSize: 10; font.weight: Font.SemiBold
                                    }
                                    MouseArea {
                                        id: songUseMa
                                        anchors.fill: parent; hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: soundsTab.extractPath = modelData.path
                                    }
                                }
                            }
                            MouseArea {
                                id: songPickMa
                                anchors.fill: parent; hoverEnabled: true
                                propagateComposedEvents: true
                                onClicked: { soundsTab.extractPath = modelData.path; mouse.accepted = false }
                            }
                        }
                    }

                    // Extract button
                    GlowButton {
                        text: "\u2702 Extract"
                        accentColor: accent
                        Layout.fillWidth: true
                        implicitHeight: 34
                        enabled: !backend.generating && soundsTab.extractPath.length > 0
                        loading: backend.generating
                        onClicked: backend.extractStems(soundsTab.extractPath,
                                                        soundsTab.extractMode)
                    }
                }

                // ── Extracted stems (styled like gen history) ─────────
                SectionLabel {
                    text: "Stems \u00B7 " + soundsTab.stems.length + " extracted"
                    accentColor: accent
                    visible: soundsTab.stems.length > 0
                }

                Repeater {
                    model: soundsTab.stems
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        height: 56
                        radius: 6
                        color: surface
                        border.color: border_

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 8

                            // Play circle
                            Rectangle {
                                width: 28; height: 28; radius: 14
                                color: stemPlayMa.containsMouse
                                       ? Qt.rgba(accent.r, accent.g, accent.b, 0.40)
                                       : Qt.rgba(accent.r, accent.g, accent.b, 0.15)
                                border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.50)
                                border.width: 1
                                Behavior on color { ColorAnimation { duration: 80 } }
                                Text {
                                    anchors.centerIn: parent
                                    text: "\u25B6"; color: accent; font.pixelSize: 9
                                }
                                MouseArea {
                                    id: stemPlayMa
                                    anchors.fill: parent; hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.previewAudio(modelData.path || "")
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    text: modelData.name || "Stem"
                                    color: text_; font.pixelSize: 11
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Row {
                                    spacing: 2
                                    Repeater {
                                        model: 20
                                        Rectangle {
                                            required property int index
                                            width: 3
                                            height: Math.max(3, (index % 5 + 1) * 3 + (index % 3) * 2)
                                            radius: 1
                                            color: Qt.rgba(accent.r, accent.g, accent.b, 0.45)
                                            anchors.bottom: parent ? parent.bottom : undefined
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                width: 64; height: 26; radius: 13
                                color: accent
                                Text {
                                    anchors.centerIn: parent
                                    text: "\u2190 Insert"; color: "#fff"; font.pixelSize: 10
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.insertStemFile(
                                        modelData.path || "",
                                        modelData.name || "Stem")
                                }
                            }
                        }
                    }
                }

                GlowButton {
                    text: "\u2190 Insert All Stems"
                    accentColor: accent
                    Layout.fillWidth: true
                    implicitHeight: 36
                    visible: soundsTab.stems.length > 0
                    enabled: !backend.generating
                    onClicked: {
                        for (var i = 0; i < soundsTab.stems.length; i++) {
                            backend.insertStemFile(
                                soundsTab.stems[i].path || "",
                                soundsTab.stems[i].name || ("Stem " + (i + 1)))
                        }
                    }
                }

                // ── Audio Inpainting card ─────────────────────────────
                GlassCard {
                    id: inpaintCard
                    Layout.fillWidth: true
                    title: "Audio Inpainting"
                    accentColor: accent

                    property string inpaintPath: ""
                    property var inpaintTracks: []

                    Text {
                        text: "Replace a section of audio with AI-generated content"
                        color: dim; font.pixelSize: 10
                        wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 6
                        Text {
                            text: inpaintCard.inpaintPath.length > 0
                                  ? inpaintCard.inpaintPath.split("/").pop().split("\\").pop()
                                  : "No file selected"
                            color: inpaintCard.inpaintPath.length > 0 ? text_ : dim
                            font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideMiddle
                        }
                        Button {
                            text: "Browse..."
                            onClicked: { var p = backend.browseAudioFile(); if (p.length > 0) inpaintCard.inpaintPath = p }
                        }
                        Button {
                            text: "Song Editor \u25BE"
                            onClicked: { inpaintCard.inpaintTracks = backend.getSongAudioTracks(); inpaintTrackMenu.visible = !inpaintTrackMenu.visible }
                        }
                    }
                    Rectangle {
                        id: inpaintTrackMenu; visible: false; Layout.fillWidth: true
                        implicitHeight: inpaintTrackCol.implicitHeight + 8; radius: 6
                        color: Qt.rgba(surface.r, surface.g, surface.b, 0.8); border.color: border_
                        ColumnLayout {
                            id: inpaintTrackCol; anchors.fill: parent; anchors.margins: 4; spacing: 2
                            Text { text: inpaintCard.inpaintTracks.length === 0 ? "No audio tracks in Song Editor" : "Pick a track:"; color: dim; font.pixelSize: 10 }
                            Repeater {
                                model: inpaintCard.inpaintTracks
                                delegate: Rectangle {
                                    required property var modelData
                                    Layout.fillWidth: true; implicitHeight: 28; radius: 4
                                    color: inpaintPickMa.containsMouse ? Qt.rgba(accent.r,accent.g,accent.b,0.12) : "transparent"
                                    Text { text: modelData.name; color: text_; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 8 }
                                    MouseArea { id: inpaintPickMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                        onClicked: { inpaintCard.inpaintPath = modelData.path; inpaintTrackMenu.visible = false }
                                    }
                                }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        Text { text: "Start (s):"; color: dim; font.pixelSize: 11 }
                        SpinBox { id: inpaintStart; from: 0; to: 600; value: 0; stepSize: 1; Layout.fillWidth: true }
                        Text { text: "End (s):"; color: dim; font.pixelSize: 11 }
                        SpinBox { id: inpaintEnd; from: 1; to: 600; value: 5; stepSize: 1; Layout.fillWidth: true }
                    }
                    TextArea {
                        id: inpaintPrompt; Layout.fillWidth: true; Layout.minimumHeight: 40
                        placeholderText: "Describe replacement audio..."
                        color: text_; font.pixelSize: 12; wrapMode: TextEdit.Wrap
                        background: Rectangle { color: Qt.rgba(surface.r, surface.g, surface.b, 0.5); radius: 4; border.color: border_ }
                    }
                    GlowButton {
                        text: "Replace Section"; accentColor: accent; Layout.fillWidth: true; implicitHeight: 34
                        enabled: !backend.generating && inpaintCard.inpaintPath.length > 0
                        loading: backend.generating
                        onClicked: backend.replaceSection(inpaintCard.inpaintPath, inpaintStart.value, inpaintEnd.value, inpaintPrompt.text)
                    }
                }

                // ── Audio Extend card ─────────────────────────────────
                GlassCard {
                    id: extendCard
                    Layout.fillWidth: true
                    title: "Extend Audio"
                    accentColor: accent

                    property string extendPath: ""
                    property var extendTracks: []

                    Text {
                        text: "Continue audio with AI-generated extension"
                        color: dim; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 6
                        Text {
                            text: extendCard.extendPath.length > 0
                                  ? extendCard.extendPath.split("/").pop().split("\\").pop()
                                  : "No file selected"
                            color: extendCard.extendPath.length > 0 ? text_ : dim
                            font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideMiddle
                        }
                        Button {
                            text: "Browse..."
                            onClicked: { var p = backend.browseAudioFile(); if (p.length > 0) extendCard.extendPath = p }
                        }
                        Button {
                            text: "Song Editor \u25BE"
                            onClicked: { extendCard.extendTracks = backend.getSongAudioTracks(); extendTrackMenu.visible = !extendTrackMenu.visible }
                        }
                    }
                    Rectangle {
                        id: extendTrackMenu; visible: false; Layout.fillWidth: true
                        implicitHeight: extendTrackCol.implicitHeight + 8; radius: 6
                        color: Qt.rgba(surface.r, surface.g, surface.b, 0.8); border.color: border_
                        ColumnLayout {
                            id: extendTrackCol; anchors.fill: parent; anchors.margins: 4; spacing: 2
                            Text { text: extendCard.extendTracks.length === 0 ? "No audio tracks in Song Editor" : "Pick a track:"; color: dim; font.pixelSize: 10 }
                            Repeater {
                                model: extendCard.extendTracks
                                delegate: Rectangle {
                                    required property var modelData
                                    Layout.fillWidth: true; implicitHeight: 28; radius: 4
                                    color: extPickMa.containsMouse ? Qt.rgba(accent.r,accent.g,accent.b,0.12) : "transparent"
                                    Text { text: modelData.name; color: text_; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 8 }
                                    MouseArea { id: extPickMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                        onClicked: { extendCard.extendPath = modelData.path; extendTrackMenu.visible = false }
                                    }
                                }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        Text { text: "Extend by (s):"; color: dim; font.pixelSize: 11 }
                        SpinBox { id: extendDuration; from: 5; to: 120; value: 30; stepSize: 5; Layout.fillWidth: true }
                    }
                    TextArea {
                        id: extendPrompt; Layout.fillWidth: true; Layout.minimumHeight: 40
                        placeholderText: "Optional style hint for extension..."
                        color: text_; font.pixelSize: 12; wrapMode: TextEdit.Wrap
                        background: Rectangle { color: Qt.rgba(surface.r, surface.g, surface.b, 0.5); radius: 4; border.color: border_ }
                    }
                    GlowButton {
                        text: "Extend"; accentColor: accent; Layout.fillWidth: true; implicitHeight: 34
                        enabled: !backend.generating && extendCard.extendPath.length > 0
                        loading: backend.generating
                        onClicked: backend.extendAudio(extendCard.extendPath, extendDuration.value, extendPrompt.text)
                    }
                }

                // ── MIDI Tools section ────────────────────────────────
                SectionLabel { text: "MIDI Tools"; accentColor: accent }

                // MIDI Extend card
                GlassCard {
                    id: midiExtCard
                    Layout.fillWidth: true
                    title: "Extend MIDI"
                    accentColor: accent

                    property string midiExtPath: ""
                    property var midiExtTracks: []

                    Text {
                        text: "Continue a MIDI track with AI-generated bars"
                        color: dim; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 6
                        Text {
                            text: midiExtCard.midiExtPath.length > 0
                                  ? midiExtCard.midiExtPath.split("/").pop().split("\\").pop()
                                  : "No MIDI file selected"
                            color: midiExtCard.midiExtPath.length > 0 ? text_ : dim
                            font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideMiddle
                        }
                        Button {
                            text: "Browse..."
                            onClicked: { var p = backend.browseAudioFile(); if (p.length > 0) midiExtCard.midiExtPath = p }
                        }
                        Button {
                            text: "Song Editor \u25BE"
                            onClicked: { midiExtCard.midiExtTracks = backend.getSongAudioTracks(); midiExtTrackMenu.visible = !midiExtTrackMenu.visible }
                        }
                    }
                    Rectangle {
                        id: midiExtTrackMenu; visible: false; Layout.fillWidth: true
                        implicitHeight: midiExtTrackCol.implicitHeight + 8; radius: 6
                        color: Qt.rgba(surface.r, surface.g, surface.b, 0.8); border.color: border_
                        ColumnLayout {
                            id: midiExtTrackCol; anchors.fill: parent; anchors.margins: 4; spacing: 2
                            Text { text: midiExtCard.midiExtTracks.length === 0 ? "No tracks in Song Editor" : "Pick a track:"; color: dim; font.pixelSize: 10 }
                            Repeater {
                                model: midiExtCard.midiExtTracks
                                delegate: Rectangle {
                                    required property var modelData
                                    Layout.fillWidth: true; implicitHeight: 28; radius: 4
                                    color: mExtPickMa.containsMouse ? Qt.rgba(accent.r,accent.g,accent.b,0.12) : "transparent"
                                    Text { text: modelData.name; color: text_; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 8 }
                                    MouseArea { id: mExtPickMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                        onClicked: { midiExtCard.midiExtPath = modelData.path; midiExtTrackMenu.visible = false }
                                    }
                                }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        Text { text: "Add bars:"; color: dim; font.pixelSize: 11 }
                        SpinBox { id: midiExtBars; from: 1; to: 32; value: 4; stepSize: 1; Layout.fillWidth: true }
                    }
                    TextArea {
                        id: midiExtPrompt; Layout.fillWidth: true; Layout.minimumHeight: 40
                        placeholderText: "Optional style hint..."
                        color: text_; font.pixelSize: 12; wrapMode: TextEdit.Wrap
                        background: Rectangle { color: Qt.rgba(surface.r, surface.g, surface.b, 0.5); radius: 4; border.color: border_ }
                    }
                    GlowButton {
                        text: "Extend MIDI"; accentColor: accent; Layout.fillWidth: true; implicitHeight: 34
                        enabled: !backend.generating && midiExtCard.midiExtPath.length > 0
                        loading: backend.generating
                        onClicked: backend.midiExtend(midiExtCard.midiExtPath, midiExtBars.value, midiExtPrompt.text)
                    }
                }

                // MIDI Recompose card
                GlassCard {
                    id: recompCard
                    Layout.fillWidth: true
                    title: "Recompose MIDI"
                    accentColor: accent

                    property string midiRecompPath: ""
                    property var recompTracks: []

                    Text {
                        text: "Replace a bar range with a new AI variation"
                        color: dim; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 6
                        Text {
                            text: recompCard.midiRecompPath.length > 0
                                  ? recompCard.midiRecompPath.split("/").pop().split("\\").pop()
                                  : "No MIDI file selected"
                            color: recompCard.midiRecompPath.length > 0 ? text_ : dim
                            font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideMiddle
                        }
                        Button {
                            text: "Browse..."
                            onClicked: { var p = backend.browseAudioFile(); if (p.length > 0) recompCard.midiRecompPath = p }
                        }
                        Button {
                            text: "Song Editor \u25BE"
                            onClicked: { recompCard.recompTracks = backend.getSongAudioTracks(); recompTrackMenu.visible = !recompTrackMenu.visible }
                        }
                    }
                    Rectangle {
                        id: recompTrackMenu; visible: false; Layout.fillWidth: true
                        implicitHeight: recompTrackCol.implicitHeight + 8; radius: 6
                        color: Qt.rgba(surface.r, surface.g, surface.b, 0.8); border.color: border_
                        ColumnLayout {
                            id: recompTrackCol; anchors.fill: parent; anchors.margins: 4; spacing: 2
                            Text { text: recompCard.recompTracks.length === 0 ? "No tracks in Song Editor" : "Pick a track:"; color: dim; font.pixelSize: 10 }
                            Repeater {
                                model: recompCard.recompTracks
                                delegate: Rectangle {
                                    required property var modelData
                                    Layout.fillWidth: true; implicitHeight: 28; radius: 4
                                    color: rcPickMa.containsMouse ? Qt.rgba(accent.r,accent.g,accent.b,0.12) : "transparent"
                                    Text { text: modelData.name; color: text_; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 8 }
                                    MouseArea { id: rcPickMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                        onClicked: { recompCard.midiRecompPath = modelData.path; recompTrackMenu.visible = false }
                                    }
                                }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        Text { text: "Start bar:"; color: dim; font.pixelSize: 11 }
                        SpinBox { id: recompStart; from: 0; to: 99; value: 0; stepSize: 1; Layout.fillWidth: true }
                        Text { text: "End bar:"; color: dim; font.pixelSize: 11 }
                        SpinBox { id: recompEnd; from: 1; to: 100; value: 4; stepSize: 1; Layout.fillWidth: true }
                    }
                    TextArea {
                        id: recompStyle; Layout.fillWidth: true; Layout.minimumHeight: 40
                        placeholderText: "Target style (e.g. jazz, ambient, energetic)..."
                        color: text_; font.pixelSize: 12; wrapMode: TextEdit.Wrap
                        background: Rectangle { color: Qt.rgba(surface.r, surface.g, surface.b, 0.5); radius: 4; border.color: border_ }
                    }
                    GlowButton {
                        text: "Recompose"; accentColor: accent; Layout.fillWidth: true; implicitHeight: 34
                        enabled: !backend.generating && recompCard.midiRecompPath.length > 0
                        loading: backend.generating
                        onClicked: backend.midiRecompose(recompCard.midiRecompPath, recompStart.value, recompEnd.value, recompStyle.text)
                    }
                }

                // MIDI Layer card
                GlassCard {
                    id: layerCard
                    Layout.fillWidth: true
                    title: "Add MIDI Layer"
                    accentColor: accent

                    property string midiLayerPath: ""
                    property var layerTracks: []

                    Text {
                        text: "Generate a complementary MIDI part from existing track"
                        color: dim; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 6
                        Text {
                            text: layerCard.midiLayerPath.length > 0
                                  ? layerCard.midiLayerPath.split("/").pop().split("\\").pop()
                                  : "No MIDI file selected"
                            color: layerCard.midiLayerPath.length > 0 ? text_ : dim
                            font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideMiddle
                        }
                        Button {
                            text: "Browse..."
                            onClicked: { var p = backend.browseAudioFile(); if (p.length > 0) layerCard.midiLayerPath = p }
                        }
                        Button {
                            text: "Song Editor \u25BE"
                            onClicked: { layerCard.layerTracks = backend.getSongAudioTracks(); layerTrackMenu.visible = !layerTrackMenu.visible }
                        }
                    }
                    Rectangle {
                        id: layerTrackMenu; visible: false; Layout.fillWidth: true
                        implicitHeight: layerTrackCol.implicitHeight + 8; radius: 6
                        color: Qt.rgba(surface.r, surface.g, surface.b, 0.8); border.color: border_
                        ColumnLayout {
                            id: layerTrackCol; anchors.fill: parent; anchors.margins: 4; spacing: 2
                            Text { text: layerCard.layerTracks.length === 0 ? "No tracks in Song Editor" : "Pick a track:"; color: dim; font.pixelSize: 10 }
                            Repeater {
                                model: layerCard.layerTracks
                                delegate: Rectangle {
                                    required property var modelData
                                    Layout.fillWidth: true; implicitHeight: 28; radius: 4
                                    color: lyPickMa.containsMouse ? Qt.rgba(accent.r,accent.g,accent.b,0.12) : "transparent"
                                    Text { text: modelData.name; color: text_; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 8 }
                                    MouseArea { id: lyPickMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                        onClicked: { layerCard.midiLayerPath = modelData.path; layerTrackMenu.visible = false }
                                    }
                                }
                            }
                        }
                    }
                    Text { text: "Layer type:"; color: dim; font.pixelSize: 11 }
                    PillTabBar {
                        id: layerTypePill; Layout.fillWidth: true
                        model: ["Harmony", "Counter-Melody", "Arpeggio", "Bass"]; accentColor: accent
                    }
                    GlowButton {
                        text: "Generate Layer"; accentColor: accent; Layout.fillWidth: true; implicitHeight: 34
                        enabled: !backend.generating && layerCard.midiLayerPath.length > 0
                        loading: backend.generating
                        onClicked: {
                            var types = ["harmony", "counter_melody", "arpeggio", "bass"]
                            backend.midiLayer(layerCard.midiLayerPath, types[layerTypePill.currentIndex] || "harmony")
                        }
                    }
                }

                // ── Reference Track Analysis ──────────────────────────
                SectionLabel { text: "Reference & Context"; accentColor: accent }

                GlassCard {
                    id: refCard
                    Layout.fillWidth: true
                    title: "Analyze Reference Track"
                    accentColor: accent

                    property string refPath: ""
                    property var refResult: null
                    property var refTracks: []

                    Connections {
                        target: backend
                        function onReferenceAnalyzed(analysis) { refCard.refResult = analysis }
                    }

                    Text {
                        text: "Analyze a reference track to extract BPM, key, and style"
                        color: dim; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 6
                        Text {
                            text: refCard.refPath.length > 0
                                  ? refCard.refPath.split("/").pop().split("\\").pop()
                                  : "No file selected"
                            color: refCard.refPath.length > 0 ? text_ : dim
                            font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideMiddle
                        }
                        Button {
                            text: "Browse..."
                            onClicked: { var p = backend.browseAudioFile(); if (p.length > 0) refCard.refPath = p }
                        }
                        Button {
                            text: "Song Editor \u25BE"
                            onClicked: { refCard.refTracks = backend.getSongAudioTracks(); refTrackMenu.visible = !refTrackMenu.visible }
                        }
                    }
                    Rectangle {
                        id: refTrackMenu; visible: false; Layout.fillWidth: true
                        implicitHeight: refTrackCol.implicitHeight + 8; radius: 6
                        color: Qt.rgba(surface.r, surface.g, surface.b, 0.8); border.color: border_
                        ColumnLayout {
                            id: refTrackCol; anchors.fill: parent; anchors.margins: 4; spacing: 2
                            Text { text: refCard.refTracks.length === 0 ? "No audio tracks in Song Editor" : "Pick a track:"; color: dim; font.pixelSize: 10 }
                            Repeater {
                                model: refCard.refTracks
                                delegate: Rectangle {
                                    required property var modelData
                                    Layout.fillWidth: true; implicitHeight: 28; radius: 4
                                    color: refPickMa.containsMouse ? Qt.rgba(accent.r,accent.g,accent.b,0.12) : "transparent"
                                    Text { text: modelData.name; color: text_; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 8 }
                                    MouseArea { id: refPickMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                        onClicked: { refCard.refPath = modelData.path; refTrackMenu.visible = false }
                                    }
                                }
                            }
                        }
                    }
                    GlowButton {
                        text: "Analyze"; accentColor: accent; Layout.fillWidth: true; implicitHeight: 34
                        enabled: !backend.generating && refCard.refPath.length > 0
                        loading: backend.generating
                        onClicked: backend.analyzeReference(refCard.refPath)
                    }
                    // Show results
                    Rectangle {
                        Layout.fillWidth: true
                        visible: refCard.refResult !== null
                        implicitHeight: refResultCol.implicitHeight + 12
                        radius: 6
                        color: Qt.rgba(accent.r, accent.g, accent.b, 0.08)
                        border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.25)

                        ColumnLayout {
                            id: refResultCol
                            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                            spacing: 3
                            Text {
                                text: refCard.refResult
                                      ? ("BPM: " + (refCard.refResult.bpm || "?")
                                         + "  Key: " + (refCard.refResult.key || "?")
                                         + " " + (refCard.refResult.scale || ""))
                                      : ""
                                color: text_; font.pixelSize: 12; font.weight: Font.SemiBold
                            }
                            Text {
                                text: refCard.refResult ? (refCard.refResult.spectral_description || "") : ""
                                color: dim; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true
                            }
                        }
                    }
                }

                // Analyze Song Material card
                GlassCard {
                    id: matCard
                    Layout.fillWidth: true
                    title: "Analyze Song Material"
                    accentColor: accent

                    property var materialResult: null

                    Connections {
                        target: backend
                        function onSongMaterialAnalyzed(analysis) { matCard.materialResult = analysis }
                    }

                    Text {
                        text: "Analyze all Song Editor tracks for key, BPM, and style context"
                        color: dim; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    GlowButton {
                        text: "Analyze Song"; accentColor: accent; Layout.fillWidth: true; implicitHeight: 34
                        enabled: !backend.generating; loading: backend.generating
                        onClicked: backend.analyzeSongMaterial()
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        visible: matCard.materialResult !== null
                        implicitHeight: matResultCol.implicitHeight + 12
                        radius: 6
                        color: Qt.rgba(accent.r, accent.g, accent.b, 0.08)
                        border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.25)

                        ColumnLayout {
                            id: matResultCol
                            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                            spacing: 3
                            Text {
                                text: {
                                    var r = matCard.materialResult
                                    if (!r) return ""
                                    var s = r.summary || {}
                                    return "BPM: " + (s.avg_bpm || "?")
                                         + "  Key: " + (s.consensus_key || "?")
                                         + " " + (s.consensus_scale || "")
                                         + "  Tracks: " + (s.track_count || 0)
                                }
                                color: text_; font.pixelSize: 12; font.weight: Font.SemiBold
                            }
                            Text {
                                text: {
                                    var r = matCard.materialResult
                                    if (!r) return ""
                                    var s = r.summary || {}
                                    return s.overall_description || ""
                                }
                                color: dim; font.pixelSize: 10; wrapMode: Text.Wrap; Layout.fillWidth: true
                            }
                        }
                    }
                }
            }
        }

        // ── Create button (Simple + Advanced tabs only) ────────────
        GlowButton {
            id: createBtn
            text: "\u266B  Create"
            accentColor: accent
            loading: backend.generating
            enabled: !backend.generating
            visible: subStack.currentIndex !== 2
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            Layout.leftMargin: 16
            Layout.rightMargin: 16

            onClicked: {
                var opts = {}
                if (modelCombo.currentIndex >= 0)
                    opts.model = backend.modelNames[modelCombo.currentIndex] === "ElevenLabs Music"
                                 ? "elevenlabs_music" : backend.modelNames[modelCombo.currentIndex]
                // Genre: from Chat tab activeGenre (shared) or Advanced combo
                if (backend.activeGenre.length > 0) {
                    opts.genre = backend.activeGenre.toLowerCase().replace(/ /g, "_")
                } else {
                    var genre = genreCombo.currentText
                    if (genre !== "(auto)") opts.genre = genre
                }
                var key = keyCombo.currentText
                if (key !== "(auto)") opts.key = key
                if (sectionChk.checked) opts.section_structure = true

                // Duration — read from active sub-tab (Simple or Advanced)
                var durText = (subStack.currentIndex === 0) ? simpleTimeCombo.currentText
                                                            : durationCombo.currentText
                if (durText !== "(auto)") {
                    var durSecs = parseInt(durText)   // "30 s" → 30
                    if (!isNaN(durSecs)) opts.duration = durSecs
                }

                // Lyrics — map combo text to backend mode
                var lyrText = (subStack.currentIndex === 0) ? simpleLyricsCombo.currentText
                                                            : lyricsCombo.currentText
                if (lyrText === "Instrumental") opts.lyrics = "instrumental"
                else if (lyrText === "Custom")  opts.lyrics = "custom"
                // "Auto" → omit; backend defaults to auto

                // Custom lyrics text
                if (lyrText === "Custom") {
                    var lyrBody = (subStack.currentIndex === 0) ? simpleLyricsArea.text
                                                                : lyricsArea.text
                    if (lyrBody.trim().length > 0) opts.lyrics_text = lyrBody.trim()
                }

                // Tempo — Advanced tab only
                if (subStack.currentIndex === 1) {
                    var tempoText = tempoCombo.currentText
                    if (tempoText !== "(auto)") {
                        var bpm = parseInt(tempoText)   // "120 BPM" → 120
                        if (!isNaN(bpm)) opts.tempo = bpm
                    }
                }

                backend.generate(promptArea.text, opts)
            }
        }

    }
}
