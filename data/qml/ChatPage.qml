import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    color: theme.bg

    readonly property color surface: theme.surface
    readonly property color accent:  theme.accent
    readonly property color text_:   theme.fg
    readonly property color dim:     theme.dim
    readonly property color border_: theme.outline
    readonly property color userBg:  theme.userBg
    readonly property color wavyBg:  theme.wavyBg

    property string outputType: "audio"   // "audio" | "midi"

    readonly property var genreList: [
        "NCS Future Bass", "Melodic Dubstep", "NCS Big Room",
        "Rage Trap", "UK Drill", "Future Bass", "Big Room",
        "Neo-Soul",  "Pop Trap", "Trap", "House", "Lo-Fi", "Ambient", "Jazz"
    ]

    function genrePromptPrefix() {
        return backend.activeGenre.length > 0
               ? backend.activeGenre + " style: "
               : ""
    }

    // ── Inline widget components ──────────────────────────────────────────────
    Component { id: noteGridComp; NoteGridWidget {} }
    Component { id: chordComp;    ChordWidget    {} }
    Component { id: beatGridComp; BeatGridWidget {} }
    Component { id: fixCardComp;  FixCardWidget  {} }

    // ─────────────────────────────────────────────────────────────────────────
    // CHAT LAYOUT
    // ─────────────────────────────────────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Chat message list
        ListView {
            id: chatList
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 8; Layout.rightMargin: 8; Layout.bottomMargin: 2
            model: backend.chatMessages
            clip: true
            spacing: 8

            onCountChanged: Qt.callLater(function() { positionViewAtEnd() })

            delegate: Rectangle {
                width: chatList.width
                implicitHeight: msgCol.implicitHeight + 20
                radius: 12
                color: isUser ? userBg : wavyBg
                anchors.leftMargin:  isUser ? 4  : 28
                anchors.rightMargin: isUser ? 28 : 4

                ColumnLayout {
                    id: msgCol
                    anchors.fill: parent; anchors.margins: 10
                    spacing: 4

                    Text {
                        text: isUser ? "You" : "\u2726 Wavy"
                        color: isUser ? "#8ab4f8" : "#81c784"
                        font.pixelSize: 11; font.weight: Font.SemiBold
                    }
                    Text {
                        text: content; color: text_; font.pixelSize: 13
                        wrapMode: Text.Wrap; Layout.fillWidth: true
                    }
                    Text {
                        visible: actions !== undefined && actions.length > 0
                        text: {
                            if (actions === undefined || actions.length === 0) return ""
                            var names = []
                            for (var i = 0; i < actions.length; i++) {
                                var t = actions[i].type; if (t) names.push(t)
                            }
                            return "\u26A1 Actions: " + names.join(", ")
                        }
                        color: "#f0e0a0"; font.pixelSize: 10
                        wrapMode: Text.Wrap; Layout.fillWidth: true
                    }

                    Loader {
                        id: inlineWidgetLoader
                        Layout.fillWidth: true
                        Layout.topMargin: 4
                        active: !isUser && typeof widget === "string" && widget !== ""
                        visible: active
                        property var wData: widgetData
                        sourceComponent: {
                            if (widget === "note_grid") return noteGridComp
                            if (widget === "chords")    return chordComp
                            if (widget === "beat_grid") return beatGridComp
                            if (widget === "mix_fixes") return fixCardComp
                            return undefined
                        }
                        onLoaded: item.widgetData = wData
                    }
                }
            }

            footer: Item {
                width: chatList.width
                height: visible ? 40 : 0
                visible: backend.generating && backend.currentPage === 1
                Row {
                    anchors.left: parent.left; anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 7
                    Repeater {
                        model: 3
                        Rectangle {
                            required property int index
                            width: 8; height: 8; radius: 4
                            color: Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.85)
                            opacity: 0.3
                            SequentialAnimation on opacity {
                                loops: Animation.Infinite
                                running: backend.generating && backend.currentPage === 1
                                PauseAnimation { duration: index * 200 }
                                NumberAnimation { to: 1.0; duration: 300; easing.type: Easing.InOutSine }
                                NumberAnimation { to: 0.3; duration: 300; easing.type: Easing.InOutSine }
                                PauseAnimation { duration: (2 - index) * 200 }
                            }
                        }
                    }
                }
            }
        }

        // Session context pill (key/scale/bpm + active genre)
        Rectangle {
            Layout.fillWidth: true
            Layout.leftMargin: 8; Layout.rightMargin: 8
            visible: {
                var ctx = backend.sessionContext
                var hasCtx = ctx !== null && ctx !== undefined &&
                             typeof ctx.key === "string" && ctx.key !== ""
                return hasCtx || backend.activeGenre.length > 0
            }
            implicitHeight: visible ? 28 : 0
            color: Qt.rgba(accent.r, accent.g, accent.b, 0.10)
            border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.35)
            border.width: 1; radius: 14

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10; anchors.rightMargin: 6
                spacing: 5
                Text { text: "\u266A"; color: accent; font.pixelSize: 12 }
                Text {
                    text: {
                        var parts = []
                        if (backend.activeGenre.length > 0) parts.push(backend.activeGenre)
                        var ctx = backend.sessionContext
                        if (ctx) {
                            if (ctx.key)   parts.push(ctx.key)
                            if (ctx.scale) parts.push(ctx.scale)
                            if (ctx.bpm)   parts.push(ctx.bpm + " BPM")
                        }
                        return parts.join(" \u00B7 ")
                    }
                    color: accent; font.pixelSize: 11; font.weight: Font.SemiBold
                    Layout.fillWidth: true
                }
                Rectangle {
                    width: 16; height: 16; radius: 8
                    color: clearCtxMa.containsMouse
                           ? Qt.rgba(accent.r, accent.g, accent.b, 0.40)
                           : Qt.rgba(accent.r, accent.g, accent.b, 0.18)
                    Behavior on color { ColorAnimation { duration: 100 } }
                    Text {
                        anchors.centerIn: parent
                        text: "\u00D7"; color: accent; font.pixelSize: 11; font.bold: true
                    }
                    MouseArea {
                        id: clearCtxMa
                        anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            backend.setActiveGenre("")
                            backend.setSessionContext({"key": null, "scale": null, "bpm": null})
                        }
                    }
                }
            }
        }

        // Input bar
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: inputCol.implicitHeight + 10
            color: Qt.rgba(surface.r * 0.92, surface.g * 0.90, surface.b * 0.92, 0.95)
            border.width: 1
            border.color: Qt.rgba(border_.r, border_.g, border_.b, 0.3)

            ColumnLayout {
                id: inputCol
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
                anchors.leftMargin: 8; anchors.rightMargin: 8
                anchors.topMargin: 5; anchors.bottomMargin: 5
                spacing: 4

                // ── Genre chip row ────────────────────────────────────
                Flow {
                    Layout.fillWidth: true
                    spacing: 4

                    Repeater {
                        model: root.genreList
                        delegate: Rectangle {
                            required property string modelData
                            readonly property bool sel: (backend && backend.activeGenre) === modelData
                            implicitWidth: gcLbl.implicitWidth + 16
                            implicitHeight: 20
                            radius: 10
                            color: sel
                                   ? Qt.rgba(accent.r, accent.g, accent.b, 0.80)
                                   : (gcMa.containsMouse
                                      ? Qt.rgba(accent.r, accent.g, accent.b, 0.18)
                                      : Qt.rgba(surface.r, surface.g, surface.b, 0.70))
                            border.color: sel ? accent
                                             : Qt.rgba(accent.r, accent.g, accent.b,
                                                       gcMa.containsMouse ? 0.5 : 0.22)
                            border.width: 1
                            Behavior on color       { ColorAnimation { duration: 90 } }
                            Behavior on border.color { ColorAnimation { duration: 90 } }
                            Text {
                                id: gcLbl
                                anchors.centerIn: parent
                                text: modelData
                                color: sel ? "#fff" : (gcMa.containsMouse ? accent : dim)
                                font.pixelSize: 9
                                font.weight: sel ? Font.SemiBold : Font.Normal
                            }
                            MouseArea {
                                id: gcMa
                                anchors.fill: parent; hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: backend.setActiveGenre(sel ? "" : modelData)
                            }
                        }
                    }
                }

                // ── Audio / MIDI toggle ───────────────────────────────
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    Text {
                        text: "Output:"
                        color: dim; font.pixelSize: 10
                    }

                    Rectangle {
                        implicitWidth: 132; implicitHeight: 22; radius: 11
                        color: Qt.rgba(surface.r, surface.g, surface.b, 0.9)
                        border.color: border_

                        Row {
                            anchors.fill: parent; anchors.margins: 2; spacing: 2

                            Rectangle {
                                width: (parent.width - 4) / 2; height: parent.height; radius: 9
                                color: root.outputType === "audio"
                                       ? Qt.rgba(accent.r, accent.g, accent.b, 0.85)
                                       : "transparent"
                                Behavior on color { ColorAnimation { duration: 110 } }
                                Text {
                                    anchors.centerIn: parent
                                    text: "Audio"
                                    color: root.outputType === "audio" ? "#fff" : dim
                                    font.pixelSize: 10; font.weight: Font.SemiBold
                                }
                                MouseArea {
                                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                    onClicked: root.outputType = "audio"
                                }
                            }

                            Rectangle {
                                width: (parent.width - 4) / 2; height: parent.height; radius: 9
                                color: root.outputType === "midi"
                                       ? Qt.rgba(accent.r, accent.g, accent.b, 0.85)
                                       : "transparent"
                                Behavior on color { ColorAnimation { duration: 110 } }
                                Text {
                                    anchors.centerIn: parent
                                    text: "MIDI"
                                    color: root.outputType === "midi" ? "#fff" : dim
                                    font.pixelSize: 10; font.weight: Font.SemiBold
                                }
                                MouseArea {
                                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                    onClicked: root.outputType = "midi"
                                }
                            }
                        }
                    }

                    Item { Layout.fillWidth: true }
                }

                // ── Text input + action buttons ───────────────────────
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    TextField {
                        id: chatInput
                        Layout.fillWidth: true; Layout.preferredHeight: 36
                        placeholderText: {
                            var g = backend.activeGenre
                            if (root.outputType === "midi") {
                                return g.length > 0
                                    ? "Describe your " + g + " MIDI\u2026"
                                    : "Describe your MIDI composition\u2026"
                            }
                            return g.length > 0
                                ? "Describe your " + g + " track\u2026"
                                : "Describe what to generate\u2026"
                        }
                        color: text_; font.pixelSize: 13
                        background: Rectangle {
                            radius: 18; color: surface
                            border.color: chatInput.activeFocus
                                          ? Qt.rgba(accent.r, accent.g, accent.b, 0.65)
                                          : border_
                            Behavior on border.color { ColorAnimation { duration: 150 } }
                        }
                        onAccepted: {
                            const t = text.trim()
                            if (t.length > 0) {
                                const full = root.genrePromptPrefix() + t
                                if (root.outputType === "midi")
                                    backend.composeArrangement(full, "arrange",
                                                               backend.newSessionId(),
                                                               backend.dawContext())
                                else
                                    backend.chatGenerate(full)
                                text = ""
                            }
                        }
                    }

                    GlowButton {
                        text: root.outputType === "midi" ? "MIDI" : "Build"
                        accentColor: accent
                        implicitWidth: 64; implicitHeight: 36
                        enabled: !backend.generating && chatInput.text.trim().length > 0
                        loading: backend.generating
                        onClicked: {
                            const t = chatInput.text.trim()
                            if (t.length > 0) {
                                const full = root.genrePromptPrefix() + t
                                if (root.outputType === "midi")
                                    backend.composeArrangement(full, "arrange",
                                                               backend.newSessionId(),
                                                               backend.dawContext())
                                else
                                    backend.chatGenerate(full)
                                chatInput.text = ""
                            }
                        }
                    }

                    Rectangle {
                        implicitWidth: 52; implicitHeight: 36; radius: 18
                        color: clearMouse.containsMouse
                               ? Qt.rgba(surface.r, surface.g, surface.b, 1.0) : "transparent"
                        border.width: 1
                        border.color: Qt.rgba(border_.r, border_.g, border_.b, 0.4)
                        Behavior on color { ColorAnimation { duration: 100 } }
                        Text { anchors.centerIn: parent; text: "Clear"; color: dim; font.pixelSize: 11 }
                        MouseArea {
                            id: clearMouse
                            anchors.fill: parent; hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: backend.clearChat()
                        }
                    }
                }
            }
        }
    }

    Shortcut {
        sequence: "Ctrl+K"
        onActivated: { chatInput.forceActiveFocus(); chatInput.selectAll() }
    }
}
