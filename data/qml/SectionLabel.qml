import QtQuick

// Section header with left accent bar
Row {
    id: root
    property string text: ""
    property color accentColor: theme.accent
    Accessible.role: Accessible.Heading
    Accessible.name: root.text
    spacing: 8

    Rectangle {
        width: 3; height: 14; radius: 1.5
        color: accentColor
        anchors.verticalCenter: parent.verticalCenter
    }
    Text {
        text: root.text
        color: theme.fg
        font.pixelSize: 12
        font.bold: true
        anchors.verticalCenter: parent.verticalCenter
    }
}
