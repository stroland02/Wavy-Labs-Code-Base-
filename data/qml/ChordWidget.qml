import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// ---------------------------------------------------------------------------
// ChordWidget — row of clickable chord chips in chat.
// widgetData: {chords:[{name,root,quality,function,color,notes:[int]}],
//              key, scale, originalPrompt}
// ---------------------------------------------------------------------------
Rectangle {
    id: root
    color: "transparent"
    implicitHeight: col.implicitHeight + 4
    implicitWidth: parent ? parent.width : 290

    property var widgetData: ({})
    property var chords: widgetData.chords || []
    property string originalPrompt: widgetData.originalPrompt || ""

    readonly property color accent:  theme.accent
    readonly property color surface: theme.surface
    readonly property color text_:   theme.fg
    readonly property color dim:     theme.dim

    // ── Arp style picker overlay ─────────────────────────────────────────────
    property bool arpPickerVisible: false

    Rectangle {
        id: arpPicker
        visible: root.arpPickerVisible
        z: 10
        anchors { left: parent.left; right: parent.right; bottom: col.top }
        anchors.bottomMargin: 4
        radius: 8
        color: Qt.rgba(root.surface.r, root.surface.g, root.surface.b, 0.97)
        border.color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.5)
        border.width: 1
        implicitHeight: arpPickerCol.implicitHeight + 16

        ColumnLayout {
            id: arpPickerCol
            anchors { left: parent.left; right: parent.right; top: parent.top }
            anchors.margins: 8
            spacing: 4

            Text {
                text: "Arp Style"
                color: root.dim; font.pixelSize: 10; font.italic: true
            }

            Repeater {
                model: ["8th", "16th", "triplet_16th", "pingpong", "random"]
                delegate: Rectangle {
                    required property string modelData
                    Layout.fillWidth: true
                    implicitHeight: 26; radius: 6
                    color: arpStyleMa.containsMouse
                           ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.2)
                           : "transparent"
                    Behavior on color { ColorAnimation { duration: 80 } }

                    Text {
                        anchors { left: parent.left; verticalCenter: parent.verticalCenter }
                        anchors.leftMargin: 8
                        text: modelData
                        color: root.text_; font.pixelSize: 11
                    }
                    MouseArea {
                        id: arpStyleMa
                        anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.arpPickerVisible = false
                            // Collect all chord notes from all chips
                            var allNotes = []
                            for (var i = 0; i < root.chords.length; i++) {
                                var c = root.chords[i]
                                if (c.notes) {
                                    for (var j = 0; j < c.notes.length; j++)
                                        allNotes.push(c.notes[j])
                                }
                            }
                            backend.generateArpeggio(allNotes, 120, modelData, 2)
                        }
                    }
                }
            }
        }
    }

    ColumnLayout {
        id: col
        anchors { left: parent.left; right: parent.right }
        spacing: 6

        // Chord chips row
        Flow {
            Layout.fillWidth: true
            spacing: 6

            Repeater {
                model: root.chords
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    readonly property var chord: modelData
                    readonly property color chipColor: Qt.color(chord.color || "#3498db")
                    readonly property bool inserted: _inserted

                    property bool _inserted: false

                    width: chordLabel.implicitWidth + 24; height: 48
                    radius: 10
                    color: chipMa.containsMouse
                           ? Qt.rgba(chipColor.r, chipColor.g, chipColor.b, 0.28)
                           : Qt.rgba(chipColor.r, chipColor.g, chipColor.b, 0.12)
                    border.color: _inserted
                                  ? Qt.rgba(0.3, 0.9, 0.3, 0.8)
                                  : Qt.rgba(chipColor.r, chipColor.g, chipColor.b,
                                            chipMa.containsMouse ? 0.7 : 0.4)
                    border.width: 1
                    Behavior on color       { ColorAnimation { duration: 100 } }
                    Behavior on border.color { ColorAnimation { duration: 100 } }

                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 1

                        Text {
                            id: chordLabel
                            text: chord.name || "?"
                            color: _inserted ? "#86efac" : text_
                            font.pixelSize: 15; font.weight: Font.SemiBold
                            horizontalAlignment: Text.AlignHCenter
                        }
                        Text {
                            text: chord.quality || ""
                            color: dim; font.pixelSize: 9
                            horizontalAlignment: Text.AlignHCenter
                            Layout.alignment: Qt.AlignHCenter
                        }
                    }

                    MouseArea {
                        id: chipMa
                        anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (chord.notes && chord.notes.length > 0) {
                                backend.insertChord(chord.notes, 0)
                                _inserted = true
                                insertTimer.start()
                            }
                        }
                    }
                    Timer {
                        id: insertTimer
                        interval: 1500
                        onTriggered: _inserted = false
                    }

                    // Tooltip showing function
                    ToolTip.visible: chipMa.containsMouse && chord.function
                    ToolTip.text: chord.function || ""
                    ToolTip.delay: 500
                }
            }
        }

        // Footer row: key label + arp button + re-suggest button
        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            Text {
                text: (widgetData.key || "") + " " + (widgetData.scale || "")
                color: dim; font.pixelSize: 10; font.italic: true
            }
            Item { Layout.fillWidth: true }
            Text {
                text: "Click chip to insert"
                color: dim; font.pixelSize: 9; font.italic: true
            }
            Item { width: 4 }

            // Arpeggiate button
            Rectangle {
                implicitWidth: arpLabel.implicitWidth + 16
                implicitHeight: 22; radius: 11
                color: root.arpPickerVisible
                       ? Qt.rgba(accent.r, accent.g, accent.b, 0.30)
                       : (arpMa.containsMouse
                          ? Qt.rgba(accent.r, accent.g, accent.b, 0.18) : "transparent")
                border.color: Qt.rgba(accent.r, accent.g, accent.b,
                                      root.arpPickerVisible ? 0.9 : 0.5)
                border.width: 1
                Behavior on color { ColorAnimation { duration: 80 } }
                Text {
                    id: arpLabel
                    anchors.centerIn: parent
                    text: "Arpeggiate \u2192"
                    color: accent; font.pixelSize: 10
                }
                MouseArea {
                    id: arpMa
                    anchors.fill: parent; hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    enabled: !backend.generating && root.chords.length > 0
                    onClicked: root.arpPickerVisible = !root.arpPickerVisible
                }
            }

            Rectangle {
                implicitWidth: resuggestLabel.implicitWidth + 16
                implicitHeight: 22; radius: 11
                color: resuggestMa.containsMouse
                       ? Qt.rgba(accent.r, accent.g, accent.b, 0.22) : "transparent"
                border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.4)
                border.width: 1
                Text {
                    id: resuggestLabel
                    anchors.centerIn: parent
                    text: "\u21BB Suggest again"
                    color: accent; font.pixelSize: 10
                }
                MouseArea {
                    id: resuggestMa
                    anchors.fill: parent; hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    enabled: !backend.generating
                    onClicked: {
                        root.arpPickerVisible = false
                        backend.getChordSuggestions(root.originalPrompt, {})
                    }
                }
            }
        }
    }
}
