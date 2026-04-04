import QtQuick
import QtQuick.Layouts

// Glass-morphism grouped section container
Rectangle {
    id: card
    property string title: ""
    property color accentColor: theme.accent
    // Set to the input item that drives focus-ring glow (e.g. promptArea)
    property var focusItem: null
    Accessible.role: Accessible.Grouping
    Accessible.name: card.title

    // Children flow into the inner ColumnLayout
    default property alias content: inner.data

    radius: 10
    implicitHeight: Math.max(48, inner.implicitHeight + 24)

    color: Qt.rgba(theme.surface.r * 0.90, theme.surface.g * 0.88, theme.surface.b * 0.90, 0.72)

    border.width: 1
    border.color: (focusItem !== null && focusItem.activeFocus)
                  ? Qt.rgba(accentColor.r, accentColor.g, accentColor.b, 0.85)
                  : Qt.rgba(accentColor.r, accentColor.g, accentColor.b, 0.22)
    Behavior on border.color { ColorAnimation { duration: 200 } }

    // Gloss strip — top ~38% of card
    Rectangle {
        anchors.top: parent.top; anchors.topMargin: 1
        anchors.left: parent.left; anchors.leftMargin: 1
        anchors.right: parent.right; anchors.rightMargin: 1
        height: parent.height * 0.38
        radius: parent.radius
        color: Qt.rgba(theme.fg.r, theme.fg.g, theme.fg.b, 0.04)
        z: 1
    }

    // Inner layout — user children appended here via default alias
    ColumnLayout {
        id: inner
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 12
        spacing: 10

        SectionLabel {
            text: card.title
            accentColor: card.accentColor
            visible: card.title.length > 0
            Layout.fillWidth: true
        }
    }
}
