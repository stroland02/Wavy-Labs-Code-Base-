import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    clip: true
    background: Rectangle { color: theme.bg }

    readonly property color bg:      theme.bg
    readonly property color surface: theme.surface
    readonly property color accent:  theme.accent
    readonly property color text_:   theme.fg
    readonly property color dim:     theme.dim
    readonly property color border_: theme.outline

    ColumnLayout {
        width: root.availableWidth
        spacing: 10

        // ── Sub-tab pill bar ─────────────────────────────────────────
        PillTabBar {
            Layout.fillWidth: true
            Layout.topMargin: 12
            Layout.leftMargin: 16
            Layout.rightMargin: 16
            model: ["Text-to-Speech", "Speech-to-Speech", "Voice Clone", "SFX"]
            currentIndex: 0
            accentColor: accent
            onTabChanged: function(idx) { vocalStack.currentIndex = idx }
        }

        StackLayout {
            id: vocalStack
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 16
            Layout.rightMargin: 16
            currentIndex: 0

            // ── TTS ──────────────────────────────────────────────────
            ColumnLayout {
                spacing: 10

                GlassCard {
                    Layout.fillWidth: true
                    title: "Text to Speak"
                    accentColor: accent
                    focusItem: ttsText

                    TextArea {
                        id: ttsText
                        Layout.fillWidth: true
                        Layout.preferredHeight: 80
                        placeholderText: "Enter text to convert to speech..."
                        color: text_
                        font.pixelSize: 13
                        wrapMode: TextEdit.Wrap
                        background: null
                    }
                }

                GlassCard {
                    Layout.fillWidth: true
                    title: "Voice Settings"
                    accentColor: accent

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2; columnSpacing: 8; rowSpacing: 8

                        Text { text: "Voice:"; color: dim; font.pixelSize: 11 }
                        ComboBox {
                            id: voiceCombo
                            Layout.fillWidth: true
                            model: backend.voiceNames
                        }

                        Text { text: "Model:"; color: dim; font.pixelSize: 11 }
                        ComboBox {
                            id: ttsModelCombo
                            Layout.fillWidth: true
                            model: ["Multilingual v2", "Flash v2.5", "English v1"]
                            property var modelIds: ["eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_monolingual_v1"]
                        }

                        Text { text: "Stability:"; color: dim; font.pixelSize: 11 }
                        RowLayout {
                            Layout.fillWidth: true
                            Slider { id: stabSlider; from: 0; to: 1; value: 0.5; Layout.fillWidth: true }
                            Text { text: stabSlider.value.toFixed(2); color: dim; font.pixelSize: 11; Layout.preferredWidth: 30 }
                        }

                        Text { text: "Similarity:"; color: dim; font.pixelSize: 11 }
                        RowLayout {
                            Layout.fillWidth: true
                            Slider { id: simSlider; from: 0; to: 1; value: 0.75; Layout.fillWidth: true }
                            Text { text: simSlider.value.toFixed(2); color: dim; font.pixelSize: 11; Layout.preferredWidth: 30 }
                        }
                    }
                }

                GlowButton {
                    text: "Generate Speech"
                    accentColor: accent
                    loading: backend.generating
                    enabled: !backend.generating
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onClicked: {
                        var voiceId = "JBFqnCBsd6RMkjVDRZzb"
                        if (voiceCombo.currentIndex >= 0 && voiceCombo.currentIndex < backend.voiceData.length)
                            voiceId = backend.voiceData[voiceCombo.currentIndex].voice_id || voiceId
                        backend.textToSpeech(ttsText.text, voiceId,
                            ttsModelCombo.modelIds[ttsModelCombo.currentIndex],
                            stabSlider.value, simSlider.value)
                    }
                }

                Item { Layout.fillHeight: true }
            }

            // ── STS ──────────────────────────────────────────────────
            ColumnLayout {
                spacing: 10
                property string stsFilePath: ""

                GlassCard {
                    Layout.fillWidth: true
                    title: "Source Audio"
                    accentColor: accent

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Text {
                            text: stsPane.stsFilePath || "No file selected."
                            color: dim; font.pixelSize: 11
                            Layout.fillWidth: true
                            elide: Text.ElideMiddle
                        }
                        Button {
                            text: "Browse..."
                            onClicked: {
                                var p = backend.browseAudioFile()
                                if (p.length > 0) stsPane.stsFilePath = p
                            }
                        }
                    }
                }

                // ── Auto-Tune card ────────────────────────────────────
                GlassCard {
                    Layout.fillWidth: true
                    title: "Auto-Tune"
                    accentColor: accent

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        // ON/OFF toggle + Key + Scale row
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            // ON/OFF pill toggle
                            Rectangle {
                                id: atToggle
                                property bool atEnabled: false
                                implicitWidth: 72; implicitHeight: 24; radius: 12
                                color: atEnabled
                                       ? Qt.rgba(accent.r, accent.g, accent.b, 0.85)
                                       : Qt.rgba(surface.r, surface.g, surface.b, 0.8)
                                border.color: Qt.rgba(accent.r, accent.g, accent.b,
                                                      atEnabled ? 1.0 : 0.4)
                                border.width: 1
                                Behavior on color { ColorAnimation { duration: 120 } }
                                Text {
                                    anchors.centerIn: parent
                                    text: atToggle.atEnabled ? "ON" : "OFF"
                                    color: atToggle.atEnabled ? "#fff" : dim
                                    font.pixelSize: 11; font.weight: Font.SemiBold
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: atToggle.atEnabled = !atToggle.atEnabled
                                }
                            }

                            Text { text: "Key:"; color: dim; font.pixelSize: 11 }
                            ComboBox {
                                id: atKeyCombo
                                Layout.preferredWidth: 60
                                model: ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
                            }

                            Text { text: "Scale:"; color: dim; font.pixelSize: 11 }
                            ComboBox {
                                id: atScaleCombo
                                Layout.fillWidth: true
                                model: ["minor","major","dorian","pentatonic","minor_pent"]
                            }
                        }

                        // Strength slider row
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Text { text: "Strength:"; color: dim; font.pixelSize: 11 }
                            Slider {
                                id: atStrengthSlider
                                Layout.fillWidth: true
                                from: 0.0; to: 1.0; value: 0.8; stepSize: 0.05
                            }
                            Text {
                                text: atStrengthSlider.value.toFixed(2)
                                color: dim; font.pixelSize: 11
                                Layout.preferredWidth: 32
                            }
                        }

                        // Apply button
                        GlowButton {
                            text: "Apply Auto-Tune"
                            accentColor: accent
                            Layout.fillWidth: true
                            implicitHeight: 32
                            enabled: !backend.generating && atToggle.atEnabled
                                     && stsPane.stsFilePath.length > 0
                            loading: backend.generating
                            onClicked: backend.pitchCorrectAudio(
                                stsPane.stsFilePath,
                                atKeyCombo.currentText,
                                atScaleCombo.currentText,
                                atStrengthSlider.value)
                        }
                    }
                }

                GlassCard {
                    Layout.fillWidth: true
                    title: "Target Voice"
                    accentColor: accent

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2; columnSpacing: 8; rowSpacing: 6
                        Text { text: "Voice:"; color: dim; font.pixelSize: 11 }
                        ComboBox {
                            id: stsVoiceCombo
                            Layout.fillWidth: true
                            model: backend.voiceNames
                        }
                    }
                }

                GlowButton {
                    text: "Convert Voice"
                    accentColor: accent
                    loading: backend.generating
                    enabled: !backend.generating
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onClicked: {
                        var voiceId = "JBFqnCBsd6RMkjVDRZzb"
                        if (stsVoiceCombo.currentIndex >= 0 && stsVoiceCombo.currentIndex < backend.voiceData.length)
                            voiceId = backend.voiceData[stsVoiceCombo.currentIndex].voice_id || voiceId
                        backend.speechToSpeech(stsPane.stsFilePath, voiceId)
                    }
                }

                Item { id: stsPane; property string stsFilePath: ""; Layout.fillHeight: true }
            }

            // ── Voice Clone ──────────────────────────────────────────
            ColumnLayout {
                spacing: 10
                property var cloneFiles: []

                GlassCard {
                    Layout.fillWidth: true
                    title: "Voice Clone Settings"
                    accentColor: accent

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2; columnSpacing: 8; rowSpacing: 6
                        Text { text: "Voice Name:"; color: dim; font.pixelSize: 11 }
                        TextField {
                            id: cloneNameField
                            Layout.fillWidth: true
                            placeholderText: "My Cloned Voice"
                            color: text_
                        }
                    }

                    SectionLabel { text: "Audio Samples"; accentColor: accent }

                    ListView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(contentHeight, 72)
                        model: clonePane.cloneFiles
                        clip: true
                        delegate: Text {
                            required property string modelData
                            text: modelData
                            color: dim; font.pixelSize: 10
                            elide: Text.ElideMiddle
                            width: parent ? parent.width : 100
                        }
                    }

                    Button {
                        text: "+ Add Audio Sample"
                        Layout.fillWidth: true
                        onClicked: {
                            var files = backend.browseAudioFiles()
                            if (files.length > 0)
                                clonePane.cloneFiles = clonePane.cloneFiles.concat(files)
                        }
                    }
                }

                GlowButton {
                    text: "Clone Voice"
                    accentColor: accent
                    loading: backend.generating
                    enabled: !backend.generating
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onClicked: backend.voiceClone(cloneNameField.text, clonePane.cloneFiles)
                }

                Item { id: clonePane; property var cloneFiles: []; Layout.fillHeight: true }
            }

            // ── SFX ──────────────────────────────────────────────────
            ColumnLayout {
                spacing: 10

                Item { Layout.preferredHeight: 2 }

                ProGate {
                    Layout.fillWidth: true
                    featureName: "SFX Generation"
                    requiredTier: "Pro"
                    visible: backend.isFreeUser
                }

                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: sfxVoxContent.implicitHeight
                    visible: !backend.isFreeUser

                    ColumnLayout {
                        id: sfxVoxContent
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        spacing: 10

                        GlassCard {
                            Layout.fillWidth: true
                            title: "Describe the Sound Effect"
                            accentColor: accent
                            focusItem: sfxVoxPrompt

                            TextArea {
                                id: sfxVoxPrompt
                                Layout.fillWidth: true
                                Layout.preferredHeight: 100
                                placeholderText: "e.g. \"Thunder crash with rain\", \"Sci-fi laser beam\""
                                color: text_; font.pixelSize: 13
                                wrapMode: TextEdit.Wrap
                                background: null
                            }
                        }

                        GlassCard {
                            Layout.fillWidth: true
                            title: "Duration"
                            accentColor: accent

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Slider {
                                    id: sfxVoxDurSlider
                                    Layout.fillWidth: true
                                    from: 1; to: 30; value: 5; stepSize: 1
                                }
                                Text {
                                    text: Math.round(sfxVoxDurSlider.value) + " s"
                                    color: text_; font.pixelSize: 12
                                    Layout.preferredWidth: 36
                                }
                            }
                        }

                        GlowButton {
                            text: "Generate SFX"
                            accentColor: accent
                            loading: backend.generating
                            enabled: !backend.generating
                            Layout.fillWidth: true
                            Layout.preferredHeight: 42
                            onClicked: backend.generateSFX(sfxVoxPrompt.text, sfxVoxDurSlider.value)
                        }

                        // ── Granular Chop ─────────────────────────────
                        SectionLabel { text: "Granular Chop"; accentColor: accent }

                        GlassCard {
                            Layout.fillWidth: true
                            title: "Audio File"
                            accentColor: accent

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Text {
                                        id: granularFileLabel
                                        property string filePath: ""
                                        text: filePath.length > 0 ? filePath : "No file selected."
                                        color: dim; font.pixelSize: 11
                                        Layout.fillWidth: true
                                        elide: Text.ElideMiddle
                                    }
                                    Button {
                                        text: "Browse..."
                                        onClicked: {
                                            var p = backend.browseAudioFile()
                                            if (p.length > 0) granularFileLabel.filePath = p
                                        }
                                    }
                                }

                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 2; columnSpacing: 8; rowSpacing: 6

                                    Text { text: "Grain ms:"; color: dim; font.pixelSize: 11 }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Slider {
                                            id: grainMsSlider
                                            from: 20; to: 500; value: 80; stepSize: 10
                                            Layout.fillWidth: true
                                        }
                                        Text { text: Math.round(grainMsSlider.value) + " ms"
                                               color: dim; font.pixelSize: 11 }
                                    }

                                    Text { text: "Pitch spread:"; color: dim; font.pixelSize: 11 }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Slider {
                                            id: pitchSpreadSlider
                                            from: 0; to: 4; value: 0.5; stepSize: 0.1
                                            Layout.fillWidth: true
                                        }
                                        Text { text: pitchSpreadSlider.value.toFixed(1) + " st"
                                               color: dim; font.pixelSize: 11 }
                                    }

                                    Text { text: "Density:"; color: dim; font.pixelSize: 11 }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Slider {
                                            id: densitySlider
                                            from: 0.1; to: 1.0; value: 0.5; stepSize: 0.05
                                            Layout.fillWidth: true
                                        }
                                        Text { text: densitySlider.value.toFixed(2)
                                               color: dim; font.pixelSize: 11 }
                                    }
                                }

                                GlowButton {
                                    text: "Granular Chop → Pad"
                                    accentColor: accent
                                    Layout.fillWidth: true
                                    implicitHeight: 32
                                    enabled: !backend.generating
                                             && granularFileLabel.filePath.length > 0
                                    loading: backend.generating
                                    onClicked: backend.granularChopAudio(
                                        granularFileLabel.filePath,
                                        grainMsSlider.value,
                                        pitchSpreadSlider.value,
                                        densitySlider.value)
                                }
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
