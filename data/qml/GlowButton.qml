import QtQuick
import QtQuick.Layouts

// Primary CTA button with bloom glow and loading dots
Item {
    id: root
    property string text: "Submit"
    property color accentColor: theme.accent
    property bool loading: false

    signal clicked()

    implicitHeight: 42
    implicitWidth: 140

    enabled: true

    Accessible.role: Accessible.Button
    Accessible.name: root.text
    Accessible.description: root.loading ? "Loading" : ""

    opacity: enabled ? 1.0 : 0.45
    Behavior on opacity { NumberAnimation { duration: 150 } }

    scale: tapHandler.pressed ? 0.97 : 1.0
    Behavior on scale { NumberAnimation { duration: 80; easing.type: Easing.OutQuad } }

    // Glow border (behind button body)
    Rectangle {
        id: glowRect
        anchors.centerIn: parent
        width: parent.width + 12
        height: parent.height + 12
        radius: height / 2
        color: "transparent"
        border.width: 6
        border.color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, glowRect._glowOpacity)
        z: 0

        property real _glowOpacity: 0

        SequentialAnimation on _glowOpacity {
            id: glowPulse
            loops: Animation.Infinite
            running: false
            NumberAnimation { to: 0.28; duration: 700; easing.type: Easing.InOutSine }
            NumberAnimation { to: 0.0;  duration: 700; easing.type: Easing.InOutSine }
        }
    }

    // Button body
    Rectangle {
        id: btnBody
        anchors.fill: parent
        radius: height / 2
        color: hoverH.hovered ? Qt.lighter(root.accentColor, 1.15) : root.accentColor
        Behavior on color { ColorAnimation { duration: 150 } }
        z: 1

    }

    // Label or 3-dot loading row
    Item {
        anchors.fill: parent
        z: 2

        Text {
            anchors.centerIn: parent
            visible: !root.loading
            text: root.text
            color: "#ffffff"
            font.pixelSize: 13
            font.bold: true
        }

        Row {
            anchors.centerIn: parent
            spacing: 6
            visible: root.loading

            Repeater {
                model: 3
                Rectangle {
                    required property int index
                    width: 7; height: 7; radius: 3.5
                    color: "#ffffff"
                    opacity: 0.3

                    SequentialAnimation on opacity {
                        loops: Animation.Infinite
                        running: root.loading
                        PauseAnimation { duration: index * 180 }
                        NumberAnimation { to: 1.0; duration: 280; easing.type: Easing.InOutSine }
                        NumberAnimation { to: 0.3; duration: 280; easing.type: Easing.InOutSine }
                        PauseAnimation { duration: (2 - index) * 180 }
                    }
                }
            }
        }
    }

    HoverHandler {
        id: hoverH
        onHoveredChanged: glowPulse.running = hovered && root.enabled
    }

    TapHandler {
        id: tapHandler
        enabled: root.enabled && !root.loading
        onTapped: root.clicked()
    }
}
