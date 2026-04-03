import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// ---------------------------------------------------------------------------
// FixCardWidget — mix critique cards with one-click Apply buttons.
// widgetData: {suggestions:[{track_name,issue,suggestion,fix_action:{type,...}}],
//              analysisText}
// ---------------------------------------------------------------------------
Rectangle {
    id: root
    color: "transparent"
    implicitHeight: cardCol.implicitHeight + 4
    implicitWidth: parent ? parent.width : 290

    property var widgetData: ({})
    property var suggestions: widgetData.suggestions || []

    readonly property color accent:  theme.accent
    readonly property color surface: theme.surface
    readonly property color text_:   theme.fg
    readonly property color dim:     theme.dim

    ColumnLayout {
        id: cardCol
        anchors { left: parent.left; right: parent.right }
        spacing: 6

        Repeater {
            model: root.suggestions
            delegate: Rectangle {
                required property var modelData
                required property int index
                readonly property var suggestion: modelData
                property bool applied: false

                Layout.fillWidth: true
                implicitHeight: cardInner.implicitHeight + 12
                radius: 8
                color: Qt.rgba(0.08, 0.05, 0.14, 0.80)
                border.color: applied
                              ? Qt.rgba(0.3, 0.9, 0.3, 0.5)
                              : Qt.rgba(accent.r, accent.g, accent.b, 0.25)
                border.width: 1

                ColumnLayout {
                    id: cardInner
                    anchors { left: parent.left; right: parent.right; top: parent.top }
                    anchors.margins: 10
                    spacing: 4

                    // Track name + issue
                    RowLayout {
                        spacing: 6
                        Rectangle {
                            width: 3; height: 14; radius: 1
                            color: accent
                        }
                        Text {
                            text: suggestion.track_name || "Track"
                            color: accent; font.pixelSize: 11; font.weight: Font.SemiBold
                        }
                        Text {
                            text: "·"; color: dim; font.pixelSize: 11
                        }
                        Text {
                            text: suggestion.issue || ""
                            color: text_; font.pixelSize: 11
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                        }
                    }

                    // Suggestion text
                    Text {
                        text: suggestion.suggestion || ""
                        color: dim; font.pixelSize: 10
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        leftPadding: 9
                    }

                    // Apply button row
                    RowLayout {
                        Layout.fillWidth: true
                        Item { Layout.fillWidth: true }

                        Rectangle {
                            implicitWidth: applyLabel.implicitWidth + 20
                            implicitHeight: 24; radius: 12
                            visible: suggestion.fix_action !== undefined
                            color: applied
                                   ? Qt.rgba(0.2, 0.7, 0.3, 0.25)
                                   : (applyMa.containsMouse
                                      ? Qt.rgba(accent.r, accent.g, accent.b, 0.28)
                                      : Qt.rgba(accent.r, accent.g, accent.b, 0.12))
                            border.color: applied
                                         ? Qt.rgba(0.3, 0.9, 0.3, 0.7)
                                         : Qt.rgba(accent.r, accent.g, accent.b, 0.55)
                            border.width: 1
                            Behavior on color { ColorAnimation { duration: 100 } }

                            Text {
                                id: applyLabel
                                anchors.centerIn: parent
                                text: applied ? "\u2713 Applied" : "Apply"
                                color: applied ? "#86efac" : accent
                                font.pixelSize: 10; font.weight: Font.SemiBold
                            }
                            MouseArea {
                                id: applyMa
                                anchors.fill: parent; hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                enabled: !applied && suggestion.fix_action !== undefined
                                onClicked: {
                                    backend.applyMixFix(suggestion.fix_action)
                                    applied = true
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
