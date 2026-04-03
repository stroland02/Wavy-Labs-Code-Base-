import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Root QML for the AI Panel — content only, nav handled by C++ sidebar
Rectangle {
    id: root
    color: theme.bg
    implicitWidth: 326   // fixed hint — prevents tab switches from shifting splitter width

    readonly property color bgColor:      theme.bg
    readonly property color surfaceColor: theme.surface
    readonly property color accentColor:  theme.accent
    readonly property color textColor:    theme.fg
    readonly property color dimColor:     theme.dim
    readonly property color borderColor:  theme.outline
    readonly property color errorBgColor: theme.errorBg
    readonly property color errorColor:   "#e74c3c"
    readonly property color successColor: "#27ae60"

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Progress indicator — shimmer sweep
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 4
            color: root.bgColor
            visible: backend.generating
            clip: true

            Rectangle {
                id: progressBar
                height: parent.height
                width: parent.width * 0.35
                radius: 2

                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0) }
                    GradientStop { position: 0.5; color: root.accentColor }
                    GradientStop { position: 1.0; color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0) }
                }

                SequentialAnimation on x {
                    loops: Animation.Infinite
                    running: backend.generating
                    NumberAnimation {
                        from: -progressBar.width
                        to: progressBar.parent ? progressBar.parent.width : 400
                        duration: 1400
                        easing.type: Easing.InOutCubic
                    }
                }
            }
        }

        // Error bar — with warning icon and dismiss button
        Rectangle {
            id: errorBar
            property bool errorDismissed: false

            Layout.fillWidth: true
            Layout.preferredHeight: visible ? errorRow.implicitHeight + 10 : 0
            color: root.errorBgColor
            visible: backend.errorText.length > 0 && !errorDismissed

            Connections {
                target: backend
                function onErrorTextChanged() { errorBar.errorDismissed = false }
            }

            RowLayout {
                id: errorRow
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                anchors.topMargin: 5
                anchors.bottomMargin: 5
                spacing: 6

                Text {
                    text: "\u26A0"
                    color: root.errorColor
                    font.pixelSize: 13
                }
                Text {
                    Layout.fillWidth: true
                    text: backend.errorText
                    color: root.errorColor
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                }
                Text {
                    text: "\u2715"
                    color: root.errorColor
                    font.pixelSize: 13
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: errorBar.errorDismissed = true
                    }
                }
            }
        }

        // ── MIDI import confirmation banner ──────────────────────────────
        Rectangle {
            id: midiConfirm
            property bool   midiVisible: false
            property string midiTitle:   ""
            property int    midiBpm:     0
            property int    songBpm:     0
            property string midiGenre:   ""
            property bool   hasGm:       false
            property bool   useMidiBpm:  true
            property bool   useGenre:    true

            Layout.fillWidth: true
            Layout.leftMargin: 8; Layout.rightMargin: 8
            Layout.preferredHeight: visible ? midiCol.implicitHeight + 20 : 0
            visible: midiVisible
            color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.08)
            border.color: Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.4)
            border.width: 1
            radius: 8

            Connections {
                target: backend
                function onMidiImportConfirm(title, midiBpm, songBpm, activeGenre, hasGmData) {
                    midiConfirm.midiTitle  = title
                    midiConfirm.midiBpm    = midiBpm
                    midiConfirm.songBpm    = songBpm
                    midiConfirm.midiGenre  = activeGenre
                    midiConfirm.hasGm      = hasGmData
                    midiConfirm.useMidiBpm = (midiBpm > 0 && midiBpm !== songBpm)
                    midiConfirm.useGenre   = true
                    midiConfirm.midiVisible = true
                }
            }

            ColumnLayout {
                id: midiCol
                anchors { left: parent.left; right: parent.right; top: parent.top }
                anchors.margins: 10
                spacing: 8

                // Title row with dismiss X
                RowLayout {
                    spacing: 6
                    Text { text: "\uD83C\uDFB5"; font.pixelSize: 13 }
                    Text {
                        Layout.fillWidth: true
                        text: "Import: " + midiConfirm.midiTitle
                        color: root.textColor; font.pixelSize: 12; font.bold: true
                        elide: Text.ElideRight
                    }
                    Text {
                        text: "\u2715"; color: root.dimColor; font.pixelSize: 13
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: { midiConfirm.midiVisible = false; backend.cancelMidiImport() }
                        }
                    }
                }

                // ── BPM section (visible only when different) ────────────
                ColumnLayout {
                    visible: midiConfirm.midiBpm > 0 && midiConfirm.midiBpm !== midiConfirm.songBpm
                    spacing: 4

                    Text {
                        text: "Tempo"
                        color: root.dimColor; font.pixelSize: 10; font.bold: true
                    }

                    // "Use MIDI BPM" radio
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 28; radius: 6
                        color: midiConfirm.useMidiBpm
                               ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.18)
                               : "transparent"
                        border.color: midiConfirm.useMidiBpm
                                      ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.5)
                                      : root.borderColor
                        border.width: 1

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 8; spacing: 6
                            Rectangle {
                                width: 14; height: 14; radius: 7
                                border.color: root.accentColor; border.width: 1
                                color: "transparent"
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 8; height: 8; radius: 4
                                    color: root.accentColor
                                    visible: midiConfirm.useMidiBpm
                                }
                            }
                            Text {
                                text: "Use MIDI tempo (" + midiConfirm.midiBpm + " BPM)"
                                color: root.textColor; font.pixelSize: 11
                            }
                        }
                        MouseArea {
                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                            onClicked: midiConfirm.useMidiBpm = true
                        }
                    }

                    // "Keep song BPM" radio
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 28; radius: 6
                        color: !midiConfirm.useMidiBpm
                               ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.18)
                               : "transparent"
                        border.color: !midiConfirm.useMidiBpm
                                      ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.5)
                                      : root.borderColor
                        border.width: 1

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 8; spacing: 6
                            Rectangle {
                                width: 14; height: 14; radius: 7
                                border.color: root.accentColor; border.width: 1
                                color: "transparent"
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 8; height: 8; radius: 4
                                    color: root.accentColor
                                    visible: !midiConfirm.useMidiBpm
                                }
                            }
                            Text {
                                text: "Keep song tempo (" + midiConfirm.songBpm + " BPM)"
                                color: root.textColor; font.pixelSize: 11
                            }
                        }
                        MouseArea {
                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                            onClicked: midiConfirm.useMidiBpm = false
                        }
                    }
                }

                // ── Instrument section (visible only when GM data exists) ─
                ColumnLayout {
                    visible: midiConfirm.hasGm
                    spacing: 4

                    Text {
                        text: "Instruments"
                        color: root.dimColor; font.pixelSize: 10; font.bold: true
                    }

                    // "Use genre presets" radio
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 28; radius: 6
                        color: midiConfirm.useGenre
                               ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.18)
                               : "transparent"
                        border.color: midiConfirm.useGenre
                                      ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.5)
                                      : root.borderColor
                        border.width: 1

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 8; spacing: 6
                            Rectangle {
                                width: 14; height: 14; radius: 7
                                border.color: root.accentColor; border.width: 1
                                color: "transparent"
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 8; height: 8; radius: 4
                                    color: root.accentColor
                                    visible: midiConfirm.useGenre
                                }
                            }
                            Text {
                                text: "Genre presets" + (midiConfirm.midiGenre.length > 0
                                      ? " (" + midiConfirm.midiGenre + ")" : "")
                                color: root.textColor; font.pixelSize: 11
                            }
                        }
                        MouseArea {
                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                            onClicked: midiConfirm.useGenre = true
                        }
                    }

                    // "Use MIDI instruments (GM)" radio
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 28; radius: 6
                        color: !midiConfirm.useGenre
                               ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.18)
                               : "transparent"
                        border.color: !midiConfirm.useGenre
                                      ? Qt.rgba(root.accentColor.r, root.accentColor.g, root.accentColor.b, 0.5)
                                      : root.borderColor
                        border.width: 1

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 8; spacing: 6
                            Rectangle {
                                width: 14; height: 14; radius: 7
                                border.color: root.accentColor; border.width: 1
                                color: "transparent"
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 8; height: 8; radius: 4
                                    color: root.accentColor
                                    visible: !midiConfirm.useGenre
                                }
                            }
                            Text {
                                text: "MIDI instruments (General MIDI)"
                                color: root.textColor; font.pixelSize: 11
                            }
                        }
                        MouseArea {
                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                            onClicked: midiConfirm.useGenre = false
                        }
                    }
                }

                // ── Action buttons ───────────────────────────────────────
                RowLayout {
                    Layout.alignment: Qt.AlignRight
                    spacing: 8

                    // Cancel
                    Rectangle {
                        implicitWidth: cancelLabel.implicitWidth + 20
                        implicitHeight: 28; radius: 6
                        color: "transparent"
                        border.color: root.borderColor; border.width: 1
                        Text {
                            id: cancelLabel
                            anchors.centerIn: parent
                            text: "Cancel"
                            color: root.dimColor; font.pixelSize: 11
                        }
                        MouseArea {
                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                midiConfirm.midiVisible = false
                                backend.cancelMidiImport()
                            }
                        }
                    }

                    // Import
                    Rectangle {
                        implicitWidth: importLabel.implicitWidth + 20
                        implicitHeight: 28; radius: 6
                        color: root.accentColor
                        Text {
                            id: importLabel
                            anchors.centerIn: parent
                            text: "Import"
                            color: "#ffffff"; font.pixelSize: 11; font.bold: true
                        }
                        MouseArea {
                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                midiConfirm.midiVisible = false
                                backend.confirmMidiImport(midiConfirm.useMidiBpm,
                                                          midiConfirm.useGenre)
                            }
                        }
                    }
                }
            }
        }

        // Page stack — index matches NAV[] in WavyShell.cpp
        // 0: Generate  1: Chat  2: Library  3: Vocal(+SFX)  4: Mix  5: Tools  6: Console
        StackLayout {
            id: pageStack
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: backend.currentPage

            GeneratePage {}
            ChatPage {}
            LibraryPage {}
            VocalPage {}
            MixPage {}
            ToolsPage {}
            ConsolePage {}
        }
    }
}
