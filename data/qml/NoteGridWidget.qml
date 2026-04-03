import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// ---------------------------------------------------------------------------
// NoteGridWidget — bar×pitch canvas shown in chat after compose.
// widgetData: {parts:[{name,color,role,note_summary:{bar:[{pitch,beat,dur,vel}]}}],
//              sessionId, bpm, key, bars}
// ---------------------------------------------------------------------------
Rectangle {
    id: root
    color: "transparent"
    implicitHeight: gridCol.implicitHeight + 8
    implicitWidth: parent ? parent.width : 290

    property var widgetData: ({})
    property var parts: widgetData.parts || []
    property string sessionId: widgetData.sessionId || ""
    property int bpm:  widgetData.bpm  || 120
    property string key: widgetData.key || "C"
    property int bars: widgetData.bars || 4

    readonly property color accent:  theme.accent
    readonly property color surface: theme.surface
    readonly property color text_:   theme.fg
    readonly property color dim:     theme.dim

    ColumnLayout {
        id: gridCol
        anchors { left: parent.left; right: parent.right }
        spacing: 6

        Repeater {
            model: root.parts
            delegate: Rectangle {
                required property var modelData
                required property int index
                Layout.fillWidth: true
                implicitHeight: partContent.implicitHeight + 10
                color: Qt.rgba(0.06, 0.04, 0.12, 0.8)
                radius: 8
                border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.3)
                border.width: 1
                clip: true

                readonly property var part: modelData
                readonly property color partColor: Qt.color(part.color || "#9b59b6")

                ColumnLayout {
                    id: partContent
                    anchors { left: parent.left; right: parent.right; top: parent.top }
                    anchors.margins: 8
                    spacing: 4

                    // Part name header
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 5
                        Rectangle {
                            width: 8; height: 8; radius: 4
                            color: partColor
                        }
                        Text {
                            text: part.name || "Track"
                            color: partColor; font.pixelSize: 11; font.weight: Font.SemiBold
                        }
                        Text {
                            text: root.key + " · " + root.bpm + " BPM"
                            color: dim; font.pixelSize: 9
                        }
                        Item { Layout.fillWidth: true }
                        Text {
                            text: (part.note_count || 0) + " notes"
                            color: dim; font.pixelSize: 9
                        }
                    }

                    // Bars row
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        Repeater {
                            model: root.bars
                            delegate: Rectangle {
                                required property int index
                                readonly property int barIdx: index
                                readonly property var barNotes:
                                    (part.note_summary && part.note_summary[barIdx.toString()]) || []
                                readonly property bool regenLoading: false

                                Layout.fillWidth: true
                                height: 48
                                color: Qt.rgba(0.10, 0.07, 0.18, 0.65)
                                radius: 5
                                border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.2)
                                clip: true

                                // Mini piano-roll canvas
                                Canvas {
                                    anchors.fill: parent
                                    anchors.margins: 3
                                    onPaint: {
                                        var ctx2 = getContext("2d")
                                        ctx2.clearRect(0, 0, width, height)
                                        var notes = barNotes
                                        if (!notes || notes.length === 0) return

                                        // Find pitch range
                                        var minP = 127, maxP = 0
                                        for (var i = 0; i < notes.length; i++) {
                                            if (notes[i].pitch < minP) minP = notes[i].pitch
                                            if (notes[i].pitch > maxP) maxP = notes[i].pitch
                                        }
                                        var range = Math.max(maxP - minP + 2, 8)
                                        var c = Qt.color(part.color || "#9b59b6")
                                        ctx2.fillStyle = Qt.rgba(c.r, c.g, c.b, 0.85)
                                        for (var j = 0; j < notes.length; j++) {
                                            var n = notes[j]
                                            var x = (n.beat / 4.0) * width
                                            var noteH = Math.max(2, height / range)
                                            var y = height - ((n.pitch - minP + 1) / range) * height
                                            var w = Math.max(2, (n.duration / 4.0) * width - 1)
                                            ctx2.fillRect(x, y - noteH / 2, w, noteH)
                                        }
                                    }
                                    Component.onCompleted: requestPaint()
                                }

                                // Regenerate button overlay at top-right
                                Rectangle {
                                    anchors.top: parent.top; anchors.right: parent.right
                                    anchors.margins: 3
                                    width: 18; height: 14; radius: 3
                                    color: regenMa.containsMouse
                                           ? Qt.rgba(accent.r, accent.g, accent.b, 0.55)
                                           : Qt.rgba(root.surface.r, root.surface.g, root.surface.b, 0.85)
                                    Text {
                                        anchors.centerIn: parent
                                        text: "\u21BB"; color: "white"; font.pixelSize: 9
                                    }
                                    MouseArea {
                                        id: regenMa
                                        anchors.fill: parent; hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            backend.regenerateBar(
                                                root.sessionId,
                                                part.name || "",
                                                barIdx,
                                                { bpm: root.bpm, key: root.key }
                                            )
                                        }
                                    }
                                }

                                // Bar label
                                Text {
                                    anchors.bottom: parent.bottom; anchors.left: parent.left
                                    anchors.margins: 3
                                    text: "B" + (barIdx + 1); color: dim; font.pixelSize: 8
                                }
                            }
                        }
                    }
                }
            }
        }

        // Insert All button
        GlowButton {
            text: "Insert All Tracks"
            accentColor: accent
            Layout.fillWidth: true
            implicitHeight: 32
            enabled: !backend.generating
            onClicked: {
                // Trigger composeArrangement with existing session (no new generation — just insert)
                backend.composeArrangement("", "arrange", root.sessionId, {})
            }
        }
    }
}
