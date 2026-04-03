import QtQuick

// Animated sliding pill tab bar
Item {
    id: root
    property var model: []
    property int currentIndex: 0
    property color accentColor: theme.accent
    signal tabChanged(int idx)

    Accessible.role: Accessible.PageTabList
    Accessible.name: "Tab bar"
    implicitHeight: 36

    // Track border
    Rectangle {
        anchors.fill: parent
        radius: 3
        color: "transparent"
        border.width: 1
        border.color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.18)
    }

    // Glow behind pill
    Rectangle {
        id: pillGlow
        y: pill.y - 4
        height: pill.height + 8
        radius: 3
        color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.18)
        z: 0
        // x and width track the animated pill
        x: pill.x - 4
        width: pill.width + 8
    }

    // Animated pill
    Rectangle {
        id: pill
        y: 4
        height: 28
        radius: 3
        color: root.accentColor
        z: 1

        Behavior on x { SpringAnimation { spring: 3.0; damping: 0.7 } }
        Behavior on width { SpringAnimation { spring: 3.0; damping: 0.7 } }
    }

    // Tab label items
    Row {
        id: tabRow
        anchors.fill: parent
        z: 2

        Repeater {
            id: tabRepeater
            model: root.model

            Item {
                required property string modelData
                required property int index

                Accessible.role: Accessible.PageTab
                Accessible.name: modelData
                Accessible.focused: root.currentIndex === index

                width: tabRow.width / Math.max(1, root.model.length)
                height: tabRow.height

                HoverHandler { id: hoverH }

                Text {
                    anchors.centerIn: parent
                    text: modelData
                    font.pixelSize: 12
                    color: {
                        if (root.currentIndex === index) return "#ffffff"
                        if (hoverH.hovered) return Qt.rgba(theme.fg.r, theme.fg.g, theme.fg.b, 0.85)
                        return Qt.rgba(theme.dim.r, theme.dim.g, theme.dim.b, 0.80)
                    }
                    Behavior on color { ColorAnimation { duration: 150 } }
                }

                TapHandler {
                    onTapped: {
                        root.currentIndex = index
                        root.tabChanged(index)
                    }
                }
            }
        }
    }

    function updatePill() {
        if (!root.model || root.model.length === 0 || root.width <= 0) return
        var tabW = root.width / root.model.length
        pill.x = root.currentIndex * tabW + 4
        pill.width = tabW - 8
    }

    onCurrentIndexChanged: Qt.callLater(updatePill)
    onWidthChanged: Qt.callLater(updatePill)
    onModelChanged: Qt.callLater(updatePill)
    Component.onCompleted: Qt.callLater(updatePill)
}
