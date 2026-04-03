import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    color: theme.bg

    readonly property color surface: theme.surface
    readonly property color accent:  theme.accent
    readonly property color text_:   theme.fg
    readonly property color dim:     theme.dim
    readonly property color border_: theme.outline

    // Language mode → accent color mapping for left bar
    readonly property var modeColors: ["#c084fc", "#3b82f6", "#10b981", "#f59e0b"]

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Toolbar
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            color: Qt.darker(surface, 1.2)

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12; anchors.rightMargin: 12
                spacing: 8

                Text { text: "Mode:"; color: dim; font.pixelSize: 11 }

                ComboBox {
                    id: modeCombo
                    model: ["Wavy DSL", "Python", "CSV Data", "JSON Data"]
                    property var modeIds: ["dsl", "python", "csv", "json_data"]
                    implicitWidth: 120
                    background: Rectangle {
                        radius: 6
                        color: Qt.rgba(surface.r, surface.g, surface.b, 0.8)
                        border.width: 1
                        border.color: Qt.rgba(border_.r, border_.g, border_.b, 0.6)
                    }
                }

                Item { Layout.fillWidth: true }

                // Color-coded status dot + text
                Row {
                    spacing: 5
                    visible: backend.statusText.length > 0
                    Rectangle {
                        width: 6; height: 6; radius: 3
                        anchors.verticalCenter: parent.verticalCenter
                        color: backend.generating ? "#f59e0b" : "#10b981"
                    }
                    Text {
                        text: backend.statusText
                        color: dim; font.pixelSize: 11
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                GlowButton {
                    text: "\u25B6  Run"
                    accentColor: "#10b981"
                    implicitWidth: 80
                    implicitHeight: 30
                    loading: backend.generating
                    enabled: !backend.generating
                    onClicked: backend.runCode(codeEdit.text,
                                               modeCombo.modeIds[modeCombo.currentIndex])
                }

                Rectangle {
                    width: studioLabel.width + 12; height: 20; radius: 4
                    color: accent
                    Text {
                        id: studioLabel
                        anchors.centerIn: parent
                        text: "Studio tier"
                        color: "#fff"; font.pixelSize: 9
                    }
                }
            }
        }

        // Editor area with left accent bar indicating language mode
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#0d1117"

            // Left accent bar
            Rectangle {
                id: modeBar
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: 3
                color: root.modeColors[Math.min(modeCombo.currentIndex, root.modeColors.length - 1)]
                Behavior on color { ColorAnimation { duration: 200 } }
            }

            ScrollView {
                anchors.fill: parent
                anchors.leftMargin: modeBar.width + 4
                anchors.margins: 4
                clip: true

                TextArea {
                    id: codeEdit
                    color: text_
                    font.family: "Consolas"
                    font.pixelSize: 12
                    wrapMode: TextEdit.NoWrap
                    background: null
                    text: "# Wavy Labs DSL example\ntempo(128)\nkey(\"C minor\")\n\n" +
                          "track(\"drums\").pattern([1,0,0,1, 0,0,1,0], bpm=128)\n" +
                          "track(\"bass\").melody([\"C2\",\"G2\",\"Bb2\",\"C3\"], duration=\"eighth\")\n" +
                          "track(\"synth\").generate(\"lush ambient pad\", key=\"C minor\")\n"
                }
            }
        }
    }
}
