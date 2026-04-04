import QtQuick
import QtQuick.Layouts

// Tier paywall card — shown when feature requires a higher plan
Rectangle {
    id: root
    property string featureName: "This Feature"
    property string requiredTier: "Pro"

    implicitHeight: 168
    radius: 10
    color: Qt.rgba(theme.surface.r * 0.90, theme.surface.g * 0.88, theme.surface.b * 0.90, 0.80)
    border.width: 1
    border.color: Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.40)

    // Gloss strip
    Rectangle {
        anchors.top: parent.top; anchors.topMargin: 1
        anchors.left: parent.left; anchors.leftMargin: 1
        anchors.right: parent.right; anchors.rightMargin: 1
        height: parent.height * 0.38
        radius: parent.radius
        color: Qt.rgba(theme.fg.r, theme.fg.g, theme.fg.b, 0.04)
    }

    ColumnLayout {
        anchors.centerIn: parent
        spacing: 10

        Text {
            text: "\uD83D\uDD12"
            font.pixelSize: 28
            Layout.alignment: Qt.AlignHCenter
        }

        Text {
            text: root.featureName
            color: theme.fg
            font.pixelSize: 14
            font.weight: Font.SemiBold
            Layout.alignment: Qt.AlignHCenter
        }

        Text {
            text: "Requires an API key to be configured"
            color: theme.dim
            font.pixelSize: 11
            Layout.alignment: Qt.AlignHCenter
        }

        GlowButton {
            text: "Configure API Keys \u2192"
            accentColor: theme.accent
            implicitWidth: 210
            implicitHeight: 38
            Layout.alignment: Qt.AlignHCenter
            onClicked: Qt.openUrlExternally("https://github.com/stroland02/Wavy-Labs-Code-Base-#api-keys")
        }
    }
}
