import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    clip: true
    background: Rectangle { color: theme.bg }

    readonly property color surface: theme.surface
    readonly property color accent:  theme.accent
    readonly property color text_:   theme.fg
    readonly property color dim:     theme.dim
    readonly property color border_: theme.outline

    ColumnLayout {
        width: root.availableWidth
        spacing: 12

        Item { Layout.preferredHeight: 12 }

        // Pro gate at top
        ProGate {
            Layout.fillWidth: true
            Layout.leftMargin: 16; Layout.rightMargin: 16
            featureName: "AI Mix & Master"
            requiredTier: "Pro"
            visible: backend.isFreeUser
        }

        // Action cards (side-by-side)
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 16; Layout.rightMargin: 16
            spacing: 10
            visible: !backend.isFreeUser

            GlassCard {
                Layout.fillWidth: true
                accentColor: accent

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text { text: "\uD83D\uDD0A"; font.pixelSize: 22; Layout.alignment: Qt.AlignHCenter }

                    Text {
                        text: "Analyze Mix"
                        color: text_
                        font.pixelSize: 13
                        font.weight: Font.SemiBold
                        Layout.alignment: Qt.AlignHCenter
                    }
                    Text {
                        text: "Get AI feedback on your mix"
                        color: dim
                        font.pixelSize: 10
                        wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignHCenter
                        Layout.fillWidth: true
                    }

                    GlowButton {
                        text: "Analyze"
                        accentColor: accent
                        loading: backend.generating
                        enabled: !backend.generating
                        implicitHeight: 36
                        Layout.fillWidth: true
                        onClicked: backend.analyzeMix()
                    }
                }
            }

            GlassCard {
                Layout.fillWidth: true
                accentColor: accent

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text { text: "\uD83C\uDF9A"; font.pixelSize: 22; Layout.alignment: Qt.AlignHCenter }

                    Text {
                        text: "Master Audio"
                        color: text_
                        font.pixelSize: 13
                        font.weight: Font.SemiBold
                        Layout.alignment: Qt.AlignHCenter
                    }
                    Text {
                        text: "AI loudness & dynamics mastering"
                        color: dim
                        font.pixelSize: 10
                        wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignHCenter
                        Layout.fillWidth: true
                    }

                    GlowButton {
                        text: "Master"
                        accentColor: accent
                        loading: backend.generating
                        enabled: !backend.generating
                        implicitHeight: 36
                        Layout.fillWidth: true
                        onClicked: backend.masterAudio()
                    }
                }
            }
        }

        // Analysis result
        GlassCard {
            Layout.fillWidth: true
            Layout.leftMargin: 16; Layout.rightMargin: 16
            title: "Analysis Result"
            accentColor: accent
            visible: backend.mixResult.length > 0

            TextArea {
                Layout.fillWidth: true
                text: backend.mixResult
                color: text_
                font.pixelSize: 12
                font.family: "Consolas"
                readOnly: true
                wrapMode: TextEdit.Wrap
                background: null
            }
        }

        // Auto-Mix — featured card with stronger accent border
        Rectangle {
            Layout.fillWidth: true
            Layout.leftMargin: 16; Layout.rightMargin: 16
            implicitHeight: autoMixLayout.implicitHeight + 24
            radius: 10
            color: Qt.rgba(surface.r * 0.90, surface.g * 0.88, surface.b * 0.90, 0.72)
            border.width: 1
            border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.40)

            // Gloss strip
            Rectangle {
                anchors.top: parent.top; anchors.topMargin: 1
                anchors.left: parent.left; anchors.leftMargin: 1
                anchors.right: parent.right; anchors.rightMargin: 1
                height: parent.height * 0.38; radius: parent.radius
                color: Qt.rgba(theme.fg.r, theme.fg.g, theme.fg.b, 0.04)
            }

            ColumnLayout {
                id: autoMixLayout
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.margins: 12
                spacing: 8

                SectionLabel { text: "AI Auto-Mix"; accentColor: accent }

                Text {
                    text: backend.statusText
                    color: dim; font.pixelSize: 11
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                    visible: backend.statusText.length > 0
                }

                GlowButton {
                    text: "\u2728 AI Auto-Mix"
                    accentColor: accent
                    loading: backend.generating
                    enabled: !backend.generating
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onClicked: backend.autoMix()
                }
            }
        }

        // ── AI FX Chain from Text (v0.12.0) ────────────────────
        GlassCard {
            id: fxCard
            Layout.fillWidth: true
            Layout.leftMargin: 16; Layout.rightMargin: 16
            title: "AI FX Chain"
            accentColor: accent
            visible: !backend.isFreeUser

            property string fxAudioPath: ""
            property var fxChainResult: []
            property var fxTracks: []

            Connections {
                target: backend
                function onFxChainApplied(fxChain, audioPath) {
                    fxCard.fxChainResult = fxChain
                }
            }

            Text {
                text: "Describe the sound you want and AI will build an FX chain"
                color: dim; font.pixelSize: 10
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            TextArea {
                id: fxPromptArea
                Layout.fillWidth: true
                Layout.minimumHeight: 48
                placeholderText: "e.g. warm lo-fi radio, ethereal reverb wash, punchy club master..."
                color: text_
                font.pixelSize: 12
                wrapMode: TextEdit.Wrap
                background: Rectangle {
                    color: Qt.rgba(surface.r, surface.g, surface.b, 0.5)
                    radius: 4; border.color: border_
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Text {
                    text: fxCard.fxAudioPath.length > 0
                          ? fxCard.fxAudioPath.split("/").pop().split("\\").pop()
                          : "No audio file (optional)"
                    color: fxCard.fxAudioPath.length > 0 ? text_ : dim
                    font.pixelSize: 11
                    Layout.fillWidth: true
                    elide: Text.ElideMiddle
                }
                Button {
                    text: "Browse..."
                    onClicked: {
                        var p = backend.browseAudioFile()
                        if (p.length > 0) fxCard.fxAudioPath = p
                    }
                }
                Button {
                    text: "Song Editor \u25BE"
                    onClicked: { fxCard.fxTracks = backend.getSongAudioTracks(); fxTrackMenu.visible = !fxTrackMenu.visible }
                }
            }
            Rectangle {
                id: fxTrackMenu; visible: false; Layout.fillWidth: true
                implicitHeight: fxTrackCol.implicitHeight + 8; radius: 6
                color: Qt.rgba(surface.r, surface.g, surface.b, 0.8); border.color: border_
                ColumnLayout {
                    id: fxTrackCol; anchors.fill: parent; anchors.margins: 4; spacing: 2
                    Text { text: fxCard.fxTracks.length === 0 ? "No audio tracks in Song Editor" : "Pick a track:"; color: dim; font.pixelSize: 10 }
                    Repeater {
                        model: fxCard.fxTracks
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true; implicitHeight: 28; radius: 4
                            color: fxPickMa.containsMouse ? Qt.rgba(accent.r,accent.g,accent.b,0.12) : "transparent"
                            Text { text: modelData.name; color: text_; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 8 }
                            MouseArea { id: fxPickMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: { fxCard.fxAudioPath = modelData.path; fxTrackMenu.visible = false }
                            }
                        }
                    }
                }
            }

            GlowButton {
                text: "Build FX Chain"
                accentColor: accent
                loading: backend.generating
                enabled: !backend.generating && fxPromptArea.text.trim().length > 0
                Layout.fillWidth: true
                implicitHeight: 36
                onClicked: backend.textToFxChain(fxPromptArea.text, fxCard.fxAudioPath)
            }

            // Show applied FX chain
            Repeater {
                model: fxCard.fxChainResult
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    implicitHeight: 28
                    radius: 4
                    color: Qt.rgba(accent.r, accent.g, accent.b, 0.08)
                    border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.2)

                    RowLayout {
                        anchors.fill: parent; anchors.margins: 6; spacing: 6
                        Text {
                            text: (index + 1) + "."
                            color: accent; font.pixelSize: 10; font.bold: true
                        }
                        Text {
                            text: modelData.name || ""
                            color: text_; font.pixelSize: 11; font.weight: Font.SemiBold
                        }
                        Text {
                            text: {
                                var params = modelData.params || {}
                                var parts = []
                                for (var k in params) parts.push(k + "=" + params[k])
                                return parts.join(", ")
                            }
                            color: dim; font.pixelSize: 10
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        Item { Layout.preferredHeight: 8 }
    }
}
