import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    clip: true
    background: Rectangle { color: theme.bg }

    readonly property color surface: theme.surface
    readonly property color accent:  theme.accent
    readonly property color text_:   theme.fg
    readonly property color dim:     theme.dim
    readonly property color border_: theme.outline

    // Styled drop-zone rectangle component (inline)
    // Note: inline components have their own scope — use theme.* directly
    component DropZone: Rectangle {
        property string filePath: ""
        property string hint: "Drop file here or Browse \u2192"
        signal browseClicked()

        Layout.fillWidth: true
        implicitHeight: 52
        radius: 8
        color: Qt.rgba(theme.surface.r, theme.surface.g, theme.surface.b, 0.5)
        border.width: 1
        border.color: Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.35)

        RowLayout {
            anchors.fill: parent; anchors.margins: 10; spacing: 8
            Text {
                Layout.fillWidth: true
                text: filePath.length > 0 ? filePath : hint
                color: filePath.length > 0 ? theme.fg : theme.dim
                font.pixelSize: 11
                elide: Text.ElideMiddle
            }
            Rectangle {
                width: 64; height: 24; radius: 12
                color: browseMouse.containsMouse ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.25) : "transparent"
                border.color: Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.5)
                Behavior on color { ColorAnimation { duration: 120 } }
                Text {
                    anchors.centerIn: parent
                    text: "Browse"
                    color: theme.accent; font.pixelSize: 10
                }
                MouseArea {
                    id: browseMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: parent.parent.parent.browseClicked()
                }
            }
        }
    }

    ColumnLayout {
        width: root.availableWidth
        spacing: 10

        // Scrollable pill tab bar for 6 tools
        ScrollView {
            Layout.fillWidth: true
            Layout.preferredHeight: 50
            Layout.topMargin: 12
            Layout.leftMargin: 8; Layout.rightMargin: 8
            clip: true
            contentWidth: toolsPillBar.implicitWidth
            contentHeight: 50
            ScrollBar.vertical.policy: ScrollBar.AlwaysOff
            ScrollBar.horizontal.policy: ScrollBar.AsNeeded

            PillTabBar {
                id: toolsPillBar
                width: Math.max(root.availableWidth - 16, model.length * 110)
                implicitWidth: model.length * 110
                height: 36
                y: 7
                model: ["Voice Isolator", "Transcribe", "Alignment",
                        "AI Dubbing", "Replace Section", "Audio\u2192MIDI",
                        "NCS Toolkit", "Instruments", "Sound Packs", "MIDI Learn"]
                currentIndex: 0
                accentColor: accent
                onTabChanged: function(idx) { toolsStack.currentIndex = idx }
            }
        }

        StackLayout {
            id: toolsStack
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 16; Layout.rightMargin: 16
            currentIndex: 0

            // ── Voice Isolator ───────────────────────────────────────
            ColumnLayout {
                spacing: 10

                GlassCard {
                    Layout.fillWidth: true
                    title: "Voice Isolator"
                    accentColor: accent

                    DropZone {
                        id: isolateZone
                        onBrowseClicked: {
                            var p = backend.browseAudioFile()
                            if (p) isolateZone.filePath = p
                        }
                    }
                }

                GlowButton {
                    text: "Isolate Vocals"
                    accentColor: accent
                    loading: backend.generating
                    enabled: !backend.generating
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onClicked: backend.voiceIsolate(isolateZone.filePath)
                }
                Item { Layout.fillHeight: true }
            }

            // ── Transcribe ───────────────────────────────────────────
            ColumnLayout {
                spacing: 10

                GlassCard {
                    Layout.fillWidth: true
                    title: "Transcribe Audio"
                    accentColor: accent

                    DropZone {
                        id: transcribeZone
                        onBrowseClicked: {
                            var p = backend.browseAudioFile()
                            if (p) transcribeZone.filePath = p
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true; columns: 2; columnSpacing: 8; rowSpacing: 6
                        Text { text: "Language:"; color: dim; font.pixelSize: 11 }
                        ComboBox {
                            id: trLangCombo; Layout.fillWidth: true
                            model: ["en","es","fr","de","it","pt","ja","ko","zh"]
                        }
                    }
                }

                GlowButton {
                    text: "Transcribe"
                    accentColor: accent
                    loading: backend.generating
                    enabled: !backend.generating
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onClicked: backend.transcribe(transcribeZone.filePath, trLangCombo.currentText)
                }

                GlassCard {
                    Layout.fillWidth: true
                    title: "Transcript"
                    accentColor: accent
                    visible: backend.transcribeResult.length > 0

                    ScrollView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 100
                        clip: true
                        TextArea {
                            text: backend.transcribeResult
                            color: text_; font.pixelSize: 12
                            readOnly: true; wrapMode: TextEdit.Wrap
                            background: null
                        }
                    }
                }
            }

            // ── Forced Alignment ─────────────────────────────────────
            ColumnLayout {
                spacing: 10

                GlassCard {
                    Layout.fillWidth: true
                    title: "Forced Alignment"
                    accentColor: accent

                    DropZone {
                        id: alignZone
                        onBrowseClicked: {
                            var p = backend.browseAudioFile()
                            if (p) alignZone.filePath = p
                        }
                    }

                    TextArea {
                        id: alignText
                        Layout.fillWidth: true; Layout.preferredHeight: 72
                        placeholderText: "Enter text to align with the audio..."
                        color: text_; font.pixelSize: 12; wrapMode: TextEdit.Wrap
                        background: Rectangle { radius: 6; color: surface; border.color: border_ }
                    }
                }

                GlowButton {
                    text: "Align"
                    accentColor: accent
                    loading: backend.generating
                    enabled: !backend.generating
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onClicked: backend.forcedAlign(alignZone.filePath, alignText.text)
                }
                Item { Layout.fillHeight: true }
            }

            // ── AI Dubbing ───────────────────────────────────────────
            ColumnLayout {
                spacing: 10

                GlassCard {
                    Layout.fillWidth: true
                    title: "AI Dubbing"
                    accentColor: accent

                    DropZone {
                        id: dubZone
                        onBrowseClicked: {
                            var p = backend.browseAudioFile()
                            if (p) dubZone.filePath = p
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true; columns: 2; columnSpacing: 8; rowSpacing: 6
                        Text { text: "Source:"; color: dim; font.pixelSize: 11 }
                        ComboBox { id: dubSrcCombo; Layout.fillWidth: true
                            model: ["en","es","fr","de","it","pt","ja","ko","zh","ar","hi","ru","pl","nl","sv","tr"] }
                        Text { text: "Target:"; color: dim; font.pixelSize: 11 }
                        ComboBox { id: dubTgtCombo; Layout.fillWidth: true; currentIndex: 1
                            model: ["en","es","fr","de","it","pt","ja","ko","zh","ar","hi","ru","pl","nl","sv","tr"] }
                    }
                }

                GlowButton {
                    text: "Dub Audio"
                    accentColor: accent
                    loading: backend.generating
                    enabled: !backend.generating
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onClicked: backend.dubAudio(dubZone.filePath, dubSrcCombo.currentText, dubTgtCombo.currentText)
                }
                Item { Layout.fillHeight: true }
            }

            // ── Replace Section ──────────────────────────────────────
            ColumnLayout {
                spacing: 10

                GlassCard {
                    Layout.fillWidth: true
                    title: "Replace Section"
                    accentColor: accent

                    DropZone {
                        id: replZone
                        onBrowseClicked: {
                            var p = backend.browseAudioFile()
                            if (p) replZone.filePath = p
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true; columns: 2; columnSpacing: 8; rowSpacing: 6
                        Text { text: "Start (s):"; color: dim; font.pixelSize: 11 }
                        SpinBox { id: replStart; from: 0; to: 36000; value: 0; editable: true; Layout.fillWidth: true }
                        Text { text: "End (s):"; color: dim; font.pixelSize: 11 }
                        SpinBox { id: replEnd; from: 0; to: 36000; value: 50; editable: true; Layout.fillWidth: true }
                    }

                    TextArea {
                        id: replPrompt
                        Layout.fillWidth: true; Layout.preferredHeight: 64
                        placeholderText: "Describe the replacement sound..."
                        color: text_; font.pixelSize: 12; wrapMode: TextEdit.Wrap
                        background: Rectangle { radius: 6; color: surface; border.color: border_ }
                    }
                }

                GlowButton {
                    text: "Replace Section"
                    accentColor: accent
                    loading: backend.generating
                    enabled: !backend.generating
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onClicked: backend.replaceSection(replZone.filePath, replStart.value / 10.0, replEnd.value / 10.0, replPrompt.text)
                }
                Item { Layout.fillHeight: true }
            }

            // ── Audio to MIDI ────────────────────────────────────────
            ColumnLayout {
                spacing: 10

                GlassCard {
                    Layout.fillWidth: true
                    title: "Audio \u2192 MIDI"
                    accentColor: accent

                    DropZone {
                        id: midiZone
                        onBrowseClicked: {
                            var p = backend.browseAudioFile()
                            if (p) midiZone.filePath = p
                        }
                    }
                }

                GlowButton {
                    text: "Convert to MIDI"
                    accentColor: accent
                    loading: backend.generating
                    enabled: !backend.generating
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onClicked: backend.audioToMidi(midiZone.filePath)
                }
                Item { Layout.fillHeight: true }
            }

            // ── NCS Toolkit ──────────────────────────────────────────
            ColumnLayout {
                id: ncsToolkitTab
                spacing: 10

                // ── Riser Generator ──────────────────────────────────
                GlassCard {
                    Layout.fillWidth: true
                    title: "Riser Generator"
                    accentColor: accent

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        PillTabBar {
                            id: riserTypePills
                            Layout.fillWidth: true
                            height: 32
                            model: ["White Noise", "Rev. Crash", "Downlifter", "Impact", "Cymbal"]
                            currentIndex: 0
                            accentColor: accent
                        }

                        GridLayout {
                            Layout.fillWidth: true; columns: 2; columnSpacing: 8; rowSpacing: 6
                            Text { text: "BPM:"; color: dim; font.pixelSize: 11 }
                            SpinBox {
                                id: riserBpm
                                from: 60; to: 200; value: 128; editable: true
                                Layout.fillWidth: true
                            }
                            Text { text: "Bars:"; color: dim; font.pixelSize: 11 }
                            ComboBox {
                                id: riserBars
                                Layout.fillWidth: true
                                model: ["0.5", "1", "2", "4", "8"]
                                currentIndex: 2
                            }
                        }

                        GlowButton {
                            text: "Generate Riser"
                            accentColor: accent
                            loading: backend.generating
                            enabled: !backend.generating
                            Layout.fillWidth: true
                            Layout.preferredHeight: 38
                            onClicked: {
                                var typeMap = ["white_noise_riser", "reverse_crash",
                                              "downlifter", "impact_hit", "cymbal_crash"]
                                backend.generateRiser(
                                    typeMap[riserTypePills.currentIndex],
                                    riserBpm.value,
                                    parseFloat(riserBars.currentText)
                                )
                            }
                        }

                        // Result row
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            visible: ncsRiserPath.length > 0

                            Text {
                                id: ncsRiserPath
                                property string path: ""
                                text: path.length > 0 ? path.split("/").pop().split("\\").pop() : ""
                                color: dim; font.pixelSize: 10
                                Layout.fillWidth: true; elide: Text.ElideMiddle
                            }
                            Rectangle {
                                width: 48; height: 24; radius: 12
                                color: playRiserMouse.containsMouse
                                       ? Qt.rgba(accent.r, accent.g, accent.b, 0.25)
                                       : "transparent"
                                border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.5)
                                Text { anchors.centerIn: parent; text: "Play"
                                       color: accent; font.pixelSize: 10 }
                                MouseArea {
                                    id: playRiserMouse; anchors.fill: parent
                                    hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.previewAudio(ncsRiserPath.path)
                                }
                            }
                            Rectangle {
                                width: 52; height: 24; radius: 12
                                color: insertRiserMouse.containsMouse
                                       ? Qt.rgba(accent.r, accent.g, accent.b, 0.25)
                                       : "transparent"
                                border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.5)
                                Text { anchors.centerIn: parent; text: "Insert"
                                       color: accent; font.pixelSize: 10 }
                                MouseArea {
                                    id: insertRiserMouse; anchors.fill: parent
                                    hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.insertStemFile(ncsRiserPath.path, "Riser")
                                }
                            }
                        }
                    }
                }

                // ── Sidechain Pump ───────────────────────────────────
                GlassCard {
                    Layout.fillWidth: true
                    title: "Sidechain Pump"
                    accentColor: accent

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        DropZone {
                            id: scZone
                            hint: "Drop audio file here or Browse \u2192"
                            onBrowseClicked: {
                                var p = backend.browseAudioFile()
                                if (p) scZone.filePath = p
                            }
                        }

                        GridLayout {
                            Layout.fillWidth: true; columns: 2; columnSpacing: 8; rowSpacing: 6
                            Text { text: "BPM:"; color: dim; font.pixelSize: 11 }
                            SpinBox { id: scBpm; from: 60; to: 200; value: 128
                                      editable: true; Layout.fillWidth: true }
                            Text { text: "Depth:"; color: dim; font.pixelSize: 11 }
                            Slider {
                                id: scDepth; Layout.fillWidth: true
                                from: 0.0; to: 1.0; value: 0.7; stepSize: 0.05
                                ToolTip.visible: pressed; ToolTip.text: value.toFixed(2)
                            }
                            Text { text: "Release (ms):"; color: dim; font.pixelSize: 11 }
                            SpinBox { id: scRelease; from: 50; to: 1000; value: 200
                                      stepSize: 50; editable: true; Layout.fillWidth: true }
                        }

                        GlowButton {
                            text: "Apply Sidechain"
                            accentColor: accent
                            loading: backend.generating
                            enabled: !backend.generating && scZone.filePath.length > 0
                            Layout.fillWidth: true
                            Layout.preferredHeight: 38
                            onClicked: backend.applySidechainPump(
                                scZone.filePath, scBpm.value,
                                scDepth.value, scRelease.value
                            )
                        }
                    }
                }

                // ── Song Structure ───────────────────────────────────
                GlassCard {
                    Layout.fillWidth: true
                    title: "Song Structure"
                    accentColor: accent

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        GridLayout {
                            Layout.fillWidth: true; columns: 2; columnSpacing: 8; rowSpacing: 6
                            Text { text: "Genre:"; color: dim; font.pixelSize: 11 }
                            ComboBox { id: ssGenre; Layout.fillWidth: true
                                model: ["Future Bass", "Trap", "House", "Lo-Fi", "Jazz", "Ambient", "808"] }
                            Text { text: "Key:"; color: dim; font.pixelSize: 11 }
                            ComboBox { id: ssKey; Layout.fillWidth: true
                                model: ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
                                currentIndex: 9 }
                            Text { text: "Scale:"; color: dim; font.pixelSize: 11 }
                            ComboBox { id: ssScale; Layout.fillWidth: true
                                model: ["minor", "major"] }
                            Text { text: "BPM:"; color: dim; font.pixelSize: 11 }
                            SpinBox { id: ssBpm; from: 60; to: 200; value: 128
                                      editable: true; Layout.fillWidth: true }
                        }

                        GlowButton {
                            text: "Generate Structure"
                            accentColor: accent
                            loading: backend.generating
                            enabled: !backend.generating
                            Layout.fillWidth: true
                            Layout.preferredHeight: 38
                            onClicked: {
                                var genreMap = {
                                    "Future Bass":  "future_bass",
                                    "Trap":         "trap",
                                    "House":        "house",
                                    "Lo-Fi":        "lofi",
                                    "Jazz":         "jazz",
                                    "Ambient":      "ambient",
                                    "808":          "808"
                                }
                                backend.getNcsSongStructure(
                                    genreMap[ssGenre.currentText] || "future_bass",
                                    ssKey.currentText,
                                    ssScale.currentText,
                                    ssBpm.value
                                )
                            }
                        }

                        // Section timeline (populated via ncsSongStructureReady signal)
                        ColumnLayout {
                            id: ssTimeline
                            Layout.fillWidth: true
                            spacing: 3
                            visible: children.length > 1   // populated dynamically

                            Repeater {
                                id: ssRepeater
                                model: ncsToolkitTab._sections
                                delegate: RowLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Rectangle {
                                        width: Math.max(40, (modelData.bars / 72.0) * (root.availableWidth - 80))
                                        height: 22; radius: 4
                                        color: Qt.rgba(accent.r, accent.g, accent.b,
                                                       0.15 + (index % 2) * 0.1)
                                        border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.4)
                                        Text {
                                            anchors.centerIn: parent
                                            text: modelData.name + " (" + modelData.bars + ")"
                                            color: text_; font.pixelSize: 9
                                            elide: Text.ElideRight
                                        }
                                    }
                                    Text {
                                        text: modelData.description
                                        color: dim; font.pixelSize: 9
                                        Layout.fillWidth: true; wrapMode: Text.Wrap
                                        visible: root.availableWidth > 340
                                    }
                                }
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                // Internal section list populated by ncsSongStructureReady signal
                property var _sections: []

                Connections {
                    target: backend
                    function onRiserReady(audioPath) {
                        ncsRiserPath.path = audioPath
                    }
                    function onNcsSongStructureReady(sections) {
                        ncsToolkitTab._sections = sections
                    }
                }
            }

            // ── Add Instrument Track ──────────────────────────────────
            ColumnLayout {
                spacing: 10

                GlassCard {
                    Layout.fillWidth: true
                    title: "Add Instrument Track"
                    accentColor: accent

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            text: "Add a new instrument track to the Song Editor"
                            color: dim; font.pixelSize: 11
                            Layout.fillWidth: true; wrapMode: Text.Wrap
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            ComboBox {
                                id: addTrackPluginCombo
                                Layout.fillWidth: true
                                model: {
                                    var plugins = backend ? backend.getAvailablePlugins() : []
                                    var names = []
                                    for (var i = 0; i < plugins.length; i++)
                                        names.push(plugins[i].displayName)
                                    return names
                                }
                                property var pluginKeys: {
                                    var plugins = backend ? backend.getAvailablePlugins() : []
                                    var keys = []
                                    for (var i = 0; i < plugins.length; i++)
                                        keys.push(plugins[i].name)
                                    return keys
                                }
                            }

                            Rectangle {
                                width: 70; height: 28; radius: 4
                                color: accent
                                Text {
                                    anchors.centerIn: parent
                                    text: "Add"; color: "#FFFFFF"
                                    font.pixelSize: 12; font.bold: true
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        var idx = addTrackPluginCombo.currentIndex
                                        var key = addTrackPluginCombo.pluginKeys[idx]
                                        var name = addTrackPluginCombo.currentText
                                        backend.addInstrumentTrack(key, name)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── Genre Instrument Config ─────────────────────────────
            ColumnLayout {
                id: instrConfigTab
                spacing: 10

                property var availablePlugins: []
                property var slotModel: []
                property string selectedGenre: "default"
                property bool hasOverride: false

                Component.onCompleted: {
                    availablePlugins = backend.getAvailablePlugins()
                }

                GlassCard {
                    Layout.fillWidth: true
                    title: "Genre Instrument Configuration"
                    accentColor: accent

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        // Genre selector
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Text { text: "Genre:"; color: dim; font.pixelSize: 12 }
                            ComboBox {
                                id: genreCombo
                                Layout.fillWidth: true
                                model: [
                                    "Default", "Future Bass", "House", "Trap",
                                    "Ambient", "Lo-Fi", "Jazz", "808"
                                ]
                                property var genreKeys: [
                                    "default", "future_bass", "house", "trap",
                                    "ambient", "lofi", "jazz", "808"
                                ]
                                onActivated: function(idx) {
                                    instrConfigTab.selectedGenre = genreKeys[idx]
                                    instrConfigTab.loadConfig()
                                }
                            }
                        }

                        // Instrument slots
                        Repeater {
                            id: slotRepeater
                            model: instrConfigTab.slotModel.length

                            Rectangle {
                                required property int index
                                Layout.fillWidth: true
                                implicitHeight: slotCol.implicitHeight + 16
                                radius: 8
                                color: Qt.rgba(theme.surface.r, theme.surface.g, theme.surface.b, 0.5)
                                border.width: 1
                                border.color: Qt.rgba(theme.outline.r, theme.outline.g, theme.outline.b, 0.3)

                                ColumnLayout {
                                    id: slotCol
                                    anchors.fill: parent; anchors.margins: 8
                                    spacing: 6

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        Text {
                                            text: "Slot " + (index + 1)
                                            color: accent; font.pixelSize: 11; font.bold: true
                                        }

                                        // Color indicator
                                        Rectangle {
                                            width: 16; height: 16; radius: 4
                                            color: instrConfigTab.slotModel[index]
                                                   ? instrConfigTab.slotModel[index].color
                                                   : theme.accent
                                            border.color: theme.outline; border.width: 1
                                        }

                                        Item { Layout.fillWidth: true }

                                        // Remove slot button
                                        Rectangle {
                                            width: 20; height: 20; radius: 10
                                            color: removeSlotMouse.containsMouse
                                                   ? Qt.rgba(1, 0.3, 0.3, 0.3) : "transparent"
                                            Text {
                                                anchors.centerIn: parent
                                                text: "\u2715"; color: dim; font.pixelSize: 11
                                            }
                                            MouseArea {
                                                id: removeSlotMouse
                                                anchors.fill: parent; hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: instrConfigTab.removeSlot(index)
                                            }
                                        }
                                    }

                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: 2; columnSpacing: 8; rowSpacing: 6

                                        Text { text: "Name:"; color: dim; font.pixelSize: 11 }
                                        TextField {
                                            id: nameField
                                            Layout.fillWidth: true
                                            text: instrConfigTab.slotModel[index]
                                                  ? instrConfigTab.slotModel[index].name : ""
                                            color: text_; font.pixelSize: 11
                                            background: Rectangle {
                                                radius: 4; color: surface
                                                border.color: border_
                                            }
                                            onTextEdited: instrConfigTab.updateSlotField(index, "name", text)
                                        }

                                        Text { text: "Plugin:"; color: dim; font.pixelSize: 11 }
                                        ComboBox {
                                            id: pluginCombo
                                            Layout.fillWidth: true
                                            model: {
                                                var names = []
                                                var plugins = instrConfigTab.availablePlugins
                                                for (var i = 0; i < plugins.length; i++)
                                                    names.push(plugins[i].displayName)
                                                return names
                                            }
                                            currentIndex: {
                                                var slot = instrConfigTab.slotModel[index]
                                                if (!slot) return 0
                                                var plugins = instrConfigTab.availablePlugins
                                                for (var i = 0; i < plugins.length; i++) {
                                                    if (plugins[i].name === slot.plugin)
                                                        return i
                                                }
                                                return 0
                                            }
                                            onActivated: function(idx) {
                                                var plugins = instrConfigTab.availablePlugins
                                                if (idx >= 0 && idx < plugins.length) {
                                                    instrConfigTab.updateSlotField(index, "plugin", plugins[idx].name)
                                                    // Refresh presets for new plugin
                                                    var presets = backend.getPresetsForPlugin(plugins[idx].displayName)
                                                    instrConfigTab.updateSlotPresets(index, presets)
                                                }
                                            }
                                        }

                                        Text { text: "Preset:"; color: dim; font.pixelSize: 11 }
                                        ComboBox {
                                            id: presetCombo
                                            Layout.fillWidth: true
                                            model: {
                                                var slot = instrConfigTab.slotModel[index]
                                                if (!slot || !slot.presetList) return ["(default)"]
                                                var items = ["(default)"]
                                                for (var i = 0; i < slot.presetList.length; i++)
                                                    items.push(slot.presetList[i])
                                                return items
                                            }
                                            currentIndex: {
                                                var slot = instrConfigTab.slotModel[index]
                                                if (!slot || !slot.preset) return 0
                                                var items = presetCombo.model
                                                for (var i = 0; i < items.length; i++) {
                                                    if (items[i] === slot.preset) return i
                                                }
                                                return 0
                                            }
                                            onActivated: function(idx) {
                                                if (idx === 0) {
                                                    instrConfigTab.updateSlotField(index, "preset", "")
                                                } else {
                                                    var items = presetCombo.model
                                                    instrConfigTab.updateSlotField(index, "preset", items[idx])
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // Add Slot button
                        Rectangle {
                            Layout.fillWidth: true
                            height: 34; radius: 8
                            color: addSlotMouse.containsMouse
                                   ? Qt.rgba(accent.r, accent.g, accent.b, 0.15)
                                   : "transparent"
                            border.width: 1
                            border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.35)
                            visible: instrConfigTab.slotModel.length < 6

                            Text {
                                anchors.centerIn: parent
                                text: "+ Add Slot"
                                color: accent; font.pixelSize: 12
                            }
                            MouseArea {
                                id: addSlotMouse
                                anchors.fill: parent; hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: instrConfigTab.addSlot()
                            }
                        }

                        // Action buttons
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            GlowButton {
                                text: "Reset to Defaults"
                                accentColor: Qt.rgba(0.9, 0.3, 0.3, 1.0)
                                Layout.fillWidth: true
                                Layout.preferredHeight: 38
                                onClicked: {
                                    backend.resetGenreInstrumentDefaults(instrConfigTab.selectedGenre)
                                    instrConfigTab.loadConfig()
                                }
                            }

                            GlowButton {
                                text: "Save Configuration"
                                accentColor: accent
                                Layout.fillWidth: true
                                Layout.preferredHeight: 38
                                onClicked: instrConfigTab.saveConfig()
                            }
                        }

                        // Status text
                        Text {
                            id: instrConfigStatus
                            Layout.fillWidth: true
                            color: accent; font.pixelSize: 11
                            horizontalAlignment: Text.AlignHCenter
                            opacity: 0
                            Behavior on opacity { NumberAnimation { duration: 300 } }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                // ── Helper functions ─────────────────────────────────
                function loadConfig() {
                    var config = backend.getGenreInstrumentConfig(selectedGenre)
                    var newModel = []
                    for (var i = 0; i < config.length; i++) {
                        var slot = config[i]
                        // Look up preset list for this plugin
                        var pluginDisplayName = pluginDisplayNameFor(slot.plugin)
                        var presets = backend.getPresetsForPlugin(pluginDisplayName)
                        slot.presetList = presets
                        newModel.push(slot)
                    }
                    slotModel = newModel
                }

                function pluginDisplayNameFor(pluginName) {
                    for (var i = 0; i < availablePlugins.length; i++) {
                        if (availablePlugins[i].name === pluginName)
                            return availablePlugins[i].displayName
                    }
                    return pluginName
                }

                function updateSlotField(idx, field, value) {
                    if (idx < 0 || idx >= slotModel.length) return
                    var copy = slotModel.slice()
                    var slot = Object.assign({}, copy[idx])
                    slot[field] = value
                    copy[idx] = slot
                    slotModel = copy
                }

                function updateSlotPresets(idx, presets) {
                    if (idx < 0 || idx >= slotModel.length) return
                    var copy = slotModel.slice()
                    var slot = Object.assign({}, copy[idx])
                    slot.presetList = presets
                    slot.preset = ""
                    copy[idx] = slot
                    slotModel = copy
                }

                function addSlot() {
                    if (slotModel.length >= 6) return
                    var copy = slotModel.slice()
                    copy.push({
                        name: "New Instrument",
                        plugin: "tripleoscillator",
                        preset: "",
                        color: accent.toString(),
                        presetList: backend.getPresetsForPlugin("TripleOscillator")
                    })
                    slotModel = copy
                }

                function removeSlot(idx) {
                    if (idx < 0 || idx >= slotModel.length) return
                    var copy = slotModel.slice()
                    copy.splice(idx, 1)
                    slotModel = copy
                }

                function saveConfig() {
                    var toSave = []
                    for (var i = 0; i < slotModel.length; i++) {
                        var s = slotModel[i]
                        toSave.push({
                            name: s.name,
                            plugin: s.plugin,
                            preset: s.preset || "",
                            color: s.color || accent.toString()
                        })
                    }
                    backend.saveGenreInstrumentOverride(selectedGenre, toSave)
                    instrConfigStatus.text = "Configuration saved for " + genreCombo.currentText
                    instrConfigStatus.opacity = 1.0
                    statusFadeTimer.restart()
                }

                Timer {
                    id: statusFadeTimer
                    interval: 2000
                    onTriggered: instrConfigStatus.opacity = 0
                }
            }

            // ── Sound Packs (SoundFont Manager) ────────────────────────
            ColumnLayout {
                id: soundPacksTab
                spacing: 10

                property var sfList: []
                property bool loaded: false

                function refresh() {
                    sfList = backend.getAvailableSoundfonts()
                    loaded = true
                }

                Component.onCompleted: refresh()

                GlassCard {
                    Layout.fillWidth: true
                    title: "Free SoundFont Packs"
                    accentColor: accent

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            text: "High-quality GM soundfonts for MIDI playback. Download once, use everywhere."
                            color: dim; font.pixelSize: 11
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }

                        Repeater {
                            model: soundPacksTab.sfList.length

                            Rectangle {
                                required property int index
                                Layout.fillWidth: true
                                implicitHeight: sfRow.implicitHeight + 16
                                radius: 8
                                color: Qt.rgba(theme.surface.r, theme.surface.g, theme.surface.b, 0.5)
                                border.width: 1
                                border.color: Qt.rgba(theme.outline.r, theme.outline.g, theme.outline.b, 0.3)

                                property var sf: soundPacksTab.sfList[index]

                                RowLayout {
                                    id: sfRow
                                    anchors.fill: parent; anchors.margins: 8
                                    spacing: 10

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2

                                        Text {
                                            text: sf ? sf.name : ""
                                            color: text_; font.pixelSize: 13; font.bold: true
                                        }
                                        Text {
                                            text: sf ? (sf.description + "  (" + sf.size_mb + " MB, " + sf.license + ")") : ""
                                            color: dim; font.pixelSize: 10
                                            wrapMode: Text.Wrap
                                            Layout.fillWidth: true
                                        }
                                    }

                                    // Status / Action buttons
                                    RowLayout {
                                        spacing: 6

                                        // Installed check
                                        Text {
                                            visible: sf && sf.installed
                                            text: "\u2714 Installed"
                                            color: "#4caf50"; font.pixelSize: 11; font.bold: true
                                        }

                                        // Download button
                                        Rectangle {
                                            visible: sf && !sf.installed
                                            width: 80; height: 28; radius: 14
                                            color: sfDlMouse.containsMouse
                                                   ? Qt.rgba(accent.r, accent.g, accent.b, 0.25)
                                                   : "transparent"
                                            border.color: accent; border.width: 1
                                            opacity: backend.generating ? 0.5 : 1.0

                                            Text {
                                                anchors.centerIn: parent
                                                text: backend.generating ? "..." : "Download"
                                                color: accent; font.pixelSize: 11
                                            }
                                            MouseArea {
                                                id: sfDlMouse
                                                anchors.fill: parent; hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                enabled: !backend.generating
                                                onClicked: {
                                                    if (sf) backend.downloadSoundfont(sf.name)
                                                }
                                            }
                                        }

                                        // Set as Default button (only for installed)
                                        Rectangle {
                                            visible: sf && sf.installed
                                            width: 90; height: 28; radius: 14
                                            color: sfDefaultMouse.containsMouse
                                                   ? Qt.rgba(accent.r, accent.g, accent.b, 0.25)
                                                   : "transparent"
                                            border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.5)
                                            border.width: 1

                                            Text {
                                                anchors.centerIn: parent
                                                text: "Set Default"
                                                color: accent; font.pixelSize: 10
                                            }
                                            MouseArea {
                                                id: sfDefaultMouse
                                                anchors.fill: parent; hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: {
                                                    if (sf) {
                                                        backend.setDefaultSoundfont(sf.path)
                                                        sfDefaultStatus.text = sf.name + " set as default"
                                                        sfDefaultStatus.opacity = 1.0
                                                        sfDefaultFadeTimer.restart()
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // Status text
                        Text {
                            id: sfDefaultStatus
                            Layout.fillWidth: true
                            color: "#4caf50"; font.pixelSize: 11
                            horizontalAlignment: Text.AlignHCenter
                            opacity: 0
                            Behavior on opacity { NumberAnimation { duration: 300 } }
                        }

                        Timer {
                            id: sfDefaultFadeTimer
                            interval: 2500
                            onTriggered: sfDefaultStatus.opacity = 0
                        }
                    }
                }

                // ── Cymatics External Link ──────────────────────────────
                GlassCard {
                    Layout.fillWidth: true
                    title: "Cymatics Free Vault"
                    accentColor: accent

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            text: "Cymatics offers premium preset packs for free. Due to licensing restrictions, they cannot be bundled with the app — download directly from their site."
                            color: dim; font.pixelSize: 11
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }

                        GlowButton {
                            text: "Browse Cymatics Free Vault"
                            accentColor: accent
                            Layout.fillWidth: true
                            Layout.preferredHeight: 38
                            onClicked: Qt.openUrlExternally("https://cymatics.fm/pages/free-download-vault")
                        }
                    }
                }

                // ── Free 808 Sample Packs ──────────────────────────────
                GlassCard {
                    Layout.fillWidth: true
                    title: "Free 808 Sample Packs"
                    accentColor: accent

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            text: "Popular free 808 kits from trusted producers. Cannot be bundled due to licensing — download directly."
                            color: dim; font.pixelSize: 11
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }

                        GlowButton {
                            text: "ProducerGrind Essential 808s"
                            accentColor: accent
                            Layout.fillWidth: true
                            Layout.preferredHeight: 38
                            onClicked: Qt.openUrlExternally("https://producergrind.com/products/essential-808s-free-808-samples")
                        }

                        GlowButton {
                            text: "BVKER Free 808 Samples"
                            accentColor: accent
                            Layout.fillWidth: true
                            Layout.preferredHeight: 38
                            onClicked: Qt.openUrlExternally("https://bfrnd.creator-spring.com/listing/free-808-samples")
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Connections {
                    target: backend
                    function onSoundfontDownloaded(name, path) {
                        soundPacksTab.refresh()
                    }
                }
            }

            // ── MIDI Learn / Controller Mapping ──────────────────────
            ColumnLayout {
                id: midiLearnTab
                spacing: 10

                property var mappings: []
                property bool learning: false
                property string learningParam: ""

                GlassCard {
                    Layout.fillWidth: true
                    title: "MIDI Controller Mapping"
                    accentColor: accent

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        Text {
                            text: "Map MIDI controllers (knobs, faders, buttons) to DAW parameters. "
                                  + "Click 'Learn' next to a parameter, then move a control on your MIDI device."
                            color: dim; font.pixelSize: 11
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }

                        // Learning indicator
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 32
                            radius: 6
                            visible: midiLearnTab.learning
                            color: Qt.rgba(1, 0.85, 0.2, 0.12)
                            border.color: Qt.rgba(1, 0.85, 0.2, 0.5)

                            RowLayout {
                                anchors.fill: parent; anchors.margins: 8; spacing: 6
                                Text {
                                    text: "\u23F3 Waiting for MIDI input for: " + midiLearnTab.learningParam
                                    color: "#ffd600"; font.pixelSize: 11
                                    Layout.fillWidth: true
                                }
                                Rectangle {
                                    width: 52; height: 22; radius: 11
                                    color: cancelLearnMa.containsMouse ? Qt.rgba(1, 0.3, 0.3, 0.3) : "transparent"
                                    border.color: Qt.rgba(1, 0.3, 0.3, 0.5)
                                    Text { anchors.centerIn: parent; text: "Cancel"; color: "#ff5252"; font.pixelSize: 10 }
                                    MouseArea {
                                        id: cancelLearnMa; anchors.fill: parent; hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: { midiLearnTab.learning = false; midiLearnTab.learningParam = "" }
                                    }
                                }
                            }
                        }

                        SectionLabel { text: "Mappable Parameters"; accentColor: accent }

                        // Parameter list
                        Repeater {
                            model: [
                                { name: "Master Volume", param: "master_volume" },
                                { name: "Master Pitch", param: "master_pitch" },
                                { name: "Track 1 Volume", param: "track_1_volume" },
                                { name: "Track 2 Volume", param: "track_2_volume" },
                                { name: "Track 3 Volume", param: "track_3_volume" },
                                { name: "Track 4 Volume", param: "track_4_volume" },
                                { name: "Tempo (BPM)", param: "tempo" }
                            ]

                            delegate: Rectangle {
                                required property var modelData
                                required property int index
                                Layout.fillWidth: true
                                implicitHeight: 36
                                radius: 6
                                color: midiParamMa.containsMouse
                                       ? Qt.rgba(accent.r, accent.g, accent.b, 0.08)
                                       : Qt.rgba(surface.r, surface.g, surface.b, 0.5)
                                border.color: Qt.rgba(border_.r, border_.g, border_.b, 0.3)

                                RowLayout {
                                    anchors.fill: parent; anchors.margins: 8; spacing: 8
                                    Text {
                                        text: modelData.name
                                        color: text_; font.pixelSize: 12
                                        Layout.fillWidth: true
                                    }

                                    // Show mapped CC if any
                                    Text {
                                        text: {
                                            for (var i = 0; i < midiLearnTab.mappings.length; i++) {
                                                if (midiLearnTab.mappings[i].param === modelData.param)
                                                    return "CC " + midiLearnTab.mappings[i].cc
                                            }
                                            return ""
                                        }
                                        color: accent; font.pixelSize: 10; font.bold: true
                                        visible: text.length > 0
                                    }

                                    Rectangle {
                                        width: 52; height: 24; radius: 12
                                        color: learnMa.containsMouse
                                               ? Qt.rgba(accent.r, accent.g, accent.b, 0.25)
                                               : "transparent"
                                        border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.5)
                                        Text {
                                            anchors.centerIn: parent
                                            text: "Learn"
                                            color: accent; font.pixelSize: 10
                                        }
                                        MouseArea {
                                            id: learnMa; anchors.fill: parent; hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                midiLearnTab.learning = true
                                                midiLearnTab.learningParam = modelData.name
                                            }
                                        }
                                    }
                                }
                                MouseArea {
                                    id: midiParamMa; anchors.fill: parent; hoverEnabled: true
                                    propagateComposedEvents: true
                                    onClicked: function(mouse) { mouse.accepted = false }
                                }
                            }
                        }

                        // Clear all mappings
                        GlowButton {
                            text: "Clear All Mappings"
                            accentColor: Qt.rgba(0.9, 0.3, 0.3, 1.0)
                            Layout.fillWidth: true
                            Layout.preferredHeight: 36
                            visible: midiLearnTab.mappings.length > 0
                            onClicked: midiLearnTab.mappings = []
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
