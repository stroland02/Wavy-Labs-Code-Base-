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

    ColumnLayout {
        width: root.availableWidth
        spacing: 12

        Item { Layout.preferredHeight: 12 }

        // Pro gate — shown when free user
        ProGate {
            Layout.fillWidth: true
            Layout.leftMargin: 16; Layout.rightMargin: 16
            featureName: "SFX Generation"
            requiredTier: "Pro"
            visible: backend.isFreeUser
        }

        // Main content — hidden when locked
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: sfxContent.implicitHeight
            visible: !backend.isFreeUser

            ColumnLayout {
                id: sfxContent
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                spacing: 12

                // Prompt card with focus glow
                GlassCard {
                    Layout.fillWidth: true
                    Layout.leftMargin: 16; Layout.rightMargin: 16
                    title: "Describe the Sound Effect"
                    accentColor: accent
                    focusItem: sfxPrompt

                    TextArea {
                        id: sfxPrompt
                        Layout.fillWidth: true
                        Layout.preferredHeight: 120
                        placeholderText: "e.g. \"Thunder crash with rain\", \"Sci-fi laser beam\""
                        color: text_; font.pixelSize: 13
                        wrapMode: TextEdit.Wrap
                        background: null
                    }
                }

                // Duration card
                GlassCard {
                    Layout.fillWidth: true
                    Layout.leftMargin: 16; Layout.rightMargin: 16
                    title: "Duration"
                    accentColor: accent

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Slider {
                            id: sfxDurSlider
                            Layout.fillWidth: true
                            from: 1; to: 30; value: 5; stepSize: 1
                        }
                        Text {
                            text: Math.round(sfxDurSlider.value) + " s"
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
                    Layout.leftMargin: 16; Layout.rightMargin: 16
                    onClicked: backend.generateSFX(sfxPrompt.text, sfxDurSlider.value)
                }
            }
        }

        Item { Layout.fillHeight: true }
    }
}
