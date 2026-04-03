import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// ---------------------------------------------------------------------------
// BeatGridWidget — 16-step drum sequencer grid in chat.
// widgetData: {rows:[{name,color,steps:[bool×16]}], bpm, bars, originalPrompt}
// ---------------------------------------------------------------------------
Rectangle {
    id: root
    color: "transparent"
    implicitHeight: gridCol.implicitHeight + 4
    implicitWidth: parent ? parent.width : 290

    property var widgetData: ({})
    // Keep a mutable copy of rows for live toggling
    property var rowData: {
        var src = widgetData.rows || []
        // Deep-copy so toggles don't mutate the model
        var copy = []
        for (var i = 0; i < src.length; i++) {
            var steps = src[i].steps ? src[i].steps.slice() : []
            copy.push({ name: src[i].name, color: src[i].color, steps: steps })
        }
        return copy
    }
    property int bpm:  widgetData.bpm  || 120
    property int bars: widgetData.bars || 1
    property string originalPrompt: widgetData.originalPrompt || ""

    readonly property color accent:  theme.accent
    readonly property color surface: theme.surface
    readonly property color text_:   theme.fg
    readonly property color dim:     theme.dim

    ColumnLayout {
        id: gridCol
        anchors { left: parent.left; right: parent.right }
        spacing: 4

        // Step grid rows
        Repeater {
            model: root.rowData
            delegate: RowLayout {
                id: rowDelegate
                required property var modelData
                required property int index
                readonly property int rowIdx: index
                readonly property var row: modelData
                readonly property color rowColor: Qt.color(row.color || "#3498db")

                Layout.fillWidth: true
                spacing: 3

                // Row name
                Text {
                    text: row.name || "–"
                    color: rowColor; font.pixelSize: 10; font.weight: Font.SemiBold
                    width: 42; elide: Text.ElideRight
                }

                // 16 step buttons
                Repeater {
                    model: 16
                    delegate: Rectangle {
                        required property int index
                        readonly property int stepIdx: index
                        readonly property bool active: row.steps ? row.steps[stepIdx] : false

                        Layout.fillWidth: true
                        height: 22; radius: 3

                        // Group separator after step 4, 8, 12
                        Layout.leftMargin: (stepIdx > 0 && stepIdx % 4 === 0) ? 3 : 0

                        color: active
                               ? Qt.rgba(rowColor.r, rowColor.g, rowColor.b, 0.85)
                               : Qt.rgba(root.surface.r, root.surface.g, root.surface.b, 0.65)
                        border.color: active
                                      ? Qt.rgba(rowColor.r, rowColor.g, rowColor.b, 1.0)
                                      : Qt.rgba(root.dim.r, root.dim.g, root.dim.b, 0.4)
                        border.width: 1
                        Behavior on color { ColorAnimation { duration: 60 } }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                // Toggle the step (mutate our copy)
                                var ri = rowDelegate.rowIdx
                                var newRows = root.rowData.slice()
                                var newRow  = { name: newRows[ri].name,
                                               color: newRows[ri].color,
                                               steps: newRows[ri].steps.slice() }
                                newRow.steps[stepIdx] = !newRow.steps[stepIdx]
                                newRows[ri] = newRow
                                root.rowData = newRows
                            }
                        }
                    }
                }
            }
        }

        // Footer: BPM + Re-roll + Insert
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            Layout.topMargin: 2

            Text { text: root.bpm + " BPM"; color: dim; font.pixelSize: 10 }
            Item { Layout.fillWidth: true }

            // Re-roll
            Rectangle {
                implicitWidth: rerollLabel.implicitWidth + 16
                implicitHeight: 26; radius: 13
                color: rerollMa.containsMouse
                       ? Qt.rgba(accent.r, accent.g, accent.b, 0.22) : "transparent"
                border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.4)
                border.width: 1
                Text {
                    id: rerollLabel
                    anchors.centerIn: parent
                    text: "\u21BB Re-roll"; color: accent; font.pixelSize: 10
                }
                MouseArea {
                    id: rerollMa
                    anchors.fill: parent; hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    enabled: !backend.generating
                    onClicked: backend.buildBeat(root.originalPrompt,
                                                 { bpm: root.bpm, bars: root.bars })
                }
            }

            // Insert
            GlowButton {
                text: "Insert"
                accentColor: accent
                implicitWidth: 72; implicitHeight: 26
                enabled: !backend.generating
                onClicked: backend.insertBeatPattern(root.rowData, root.bpm, root.bars)
            }
        }
    }
}
