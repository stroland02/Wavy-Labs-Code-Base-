import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    color: theme ? theme.bg : "#09060f"

    // ── State ─────────────────────────────────────────────────────────────────
    property bool accountOpen: false
    property bool recentOpen:  false

    // ── Theme helpers ─────────────────────────────────────────────────────────
    // true for midnight/ruby (dark bg), false for silver (light bg)
    property bool isDark: theme ? (theme.bg.r + theme.bg.g + theme.bg.b < 1.5) : true

    // Text colors derived from theme.fg
    property color textPrimary:   theme ? Qt.rgba(theme.fg.r, theme.fg.g, theme.fg.b, 0.88) : Qt.rgba(1,1,1,0.88)
    property color textSecondary: theme ? Qt.rgba(theme.fg.r, theme.fg.g, theme.fg.b, 0.60) : Qt.rgba(1,1,1,0.60)
    property color textMuted:     theme ? Qt.rgba(theme.fg.r, theme.fg.g, theme.fg.b, 0.30) : Qt.rgba(1,1,1,0.30)

    // Card surface from theme.surface
    property color cardSurface:     theme ? Qt.rgba(theme.surface.r * 0.92, theme.surface.g * 0.90, theme.surface.b * 0.90, 0.78) : Qt.rgba(0.08,0.05,0.17,0.76)
    property color cardSurfaceHov:  theme ? Qt.rgba(theme.surface.r * 0.87, theme.surface.g * 0.84, theme.surface.b * 0.84, 0.90) : Qt.rgba(0.14,0.09,0.26,0.88)

    // Hover/border overlays — white-tint for dark, black-tint for light
    property color overlayNormal: isDark ? Qt.rgba(1,1,1,0.07) : Qt.rgba(0,0,0,0.05)
    property color overlayHover:  isDark ? Qt.rgba(1,1,1,0.13) : Qt.rgba(0,0,0,0.09)
    property color overlayBorder: isDark ? Qt.rgba(1,1,1,0.12) : Qt.rgba(0,0,0,0.12)

    // Popup/panel backgrounds
    property color panelBg: {
        if (!theme) return Qt.rgba(0.07,0.04,0.13,0.97)
        if (isDark) return Qt.rgba(theme.surface.r * 0.68, theme.surface.g * 0.58, theme.surface.b * 0.58, 0.97)
        return Qt.rgba(theme.surface.r * 0.92, theme.surface.g * 0.90, theme.surface.b * 0.90, 0.98)
    }
    property color panelBorder: isDark ? Qt.rgba(1,1,1,0.10) : Qt.rgba(0,0,0,0.12)

    // Repaint canvas when theme switches
    Connections {
        target: theme
        function onChanged() { bgCanvas.requestPaint() }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────
    property string displayName: {
        var email = backend.userEmail
        if (!email || email === "") return "There"
        var local = email.split("@")[0]
        return local.charAt(0).toUpperCase() + local.slice(1)
    }

    // ── Grid background ───────────────────────────────────────────────────────
    Canvas {
        id: bgCanvas
        anchors.fill: parent
        z: 0
        onWidthChanged:  requestPaint()
        onHeightChanged: requestPaint()

        onPaint: {
            var ctx  = getContext("2d")
            var w    = width, h = height
            var cell = 40
            var dark = root.isDark

            // Base fill — theme background
            var bg = theme ? theme.bg : Qt.rgba(0.035, 0.024, 0.059, 1)
            ctx.fillStyle = bg.toString()
            ctx.fillRect(0, 0, w, h)

            // Grid lines
            ctx.strokeStyle = dark ? "rgba(255,255,255,0.030)" : "rgba(0,0,0,0.055)"
            ctx.lineWidth = 1
            ctx.beginPath()
            for (var x = cell; x < w; x += cell) { ctx.moveTo(x+0.5, 0); ctx.lineTo(x+0.5, h) }
            for (var y = cell; y < h; y += cell) { ctx.moveTo(0, y+0.5); ctx.lineTo(w, y+0.5) }
            ctx.stroke()

            // Accent-tinted dots at intersections
            var ac = theme ? theme.accent : Qt.rgba(0.49, 0.23, 0.93, 1)
            var dr = Math.round(ac.r * 255)
            var dg = Math.round(ac.g * 255)
            var db = Math.round(ac.b * 255)
            ctx.fillStyle = "rgba(" + dr + "," + dg + "," + db + "," + (dark ? 0.22 : 0.28) + ")"
            for (var xi = cell; xi < w; xi += cell) {
                for (var yi = cell; yi < h; yi += cell) {
                    ctx.beginPath(); ctx.arc(xi, yi, 1.0, 0, 6.2832); ctx.fill()
                }
            }

            // Radial vignette
            var vig = ctx.createRadialGradient(w*0.5, h*0.5, h*0.18, w*0.5, h*0.5, h*0.90)
            vig.addColorStop(0, "rgba(0,0,0,0)")
            vig.addColorStop(1, dark ? "rgba(0,0,0,0.78)" : "rgba(0,0,0,0.14)")
            ctx.fillStyle = vig
            ctx.fillRect(0, 0, w, h)
        }
    }

    // ── Main layout ───────────────────────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── SPACER above hero text ───────────────────────────────────────────
        Item { Layout.fillHeight: true }

        // ── TYPEWRITER HERO TEXT ───────────────────────────────────────────────
        Item {
            id: heroItem
            Layout.fillWidth: true
            height: 72

            // ── Prompts ──────────────────────────────────────────────────────
            property var prompts: [
                "Build a trap beat from scratch",
                "Turn this vocal into a platinum hit",
                "Master this track for Spotify & Apple Music",
                "Isolate the drums and bass from this mix",
                "Write hook lyrics for this chord progression",
                "Transcribe this sample to MIDI",
                "Generate a chord progression in C minor",
                "Make this 808 bass hit harder",
                "Add energy and tension to the drop",
                "Clean up the noise in this recording",
            ]
            property int    promptIdx:   0
            property string targetText:  prompts[0]
            property string displayText: ""
            property string typeState:   "waiting"  // typing | holding | deleting | waiting
            property bool   cursorOn:    true

            // Shuffle prompts on every launch so order is always different
            Component.onCompleted: {
                var arr = prompts.slice()
                for (var i = arr.length - 1; i > 0; i--) {
                    var j = Math.floor(Math.random() * (i + 1))
                    var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp
                }
                prompts = arr
                targetText = arr[0]
            }

            // Cursor blink
            Timer {
                interval: 530; running: true; repeat: true
                onTriggered: heroItem.cursorOn = !heroItem.cursorOn
            }

            // Typewriter engine
            Timer {
                id: typeTimer
                interval: 80; running: true; repeat: true
                onTriggered: {
                    if (heroItem.typeState === "typing") {
                        if (heroItem.displayText.length < heroItem.targetText.length) {
                            heroItem.displayText = heroItem.targetText.substring(0, heroItem.displayText.length + 1)
                            interval = 42 + Math.floor(Math.random() * 58)   // 42–100ms natural variation
                        } else {
                            heroItem.typeState = "holding"
                            interval = 2400
                        }
                    } else if (heroItem.typeState === "holding") {
                        heroItem.typeState = "deleting"
                        interval = 28
                    } else if (heroItem.typeState === "deleting") {
                        if (heroItem.displayText.length > 0) {
                            heroItem.displayText = heroItem.displayText.substring(0, heroItem.displayText.length - 1)
                            interval = 22 + Math.floor(Math.random() * 18)   // 22–40ms fast delete
                        } else {
                            heroItem.typeState = "waiting"
                            interval = 500
                        }
                    } else {   // waiting
                        heroItem.promptIdx = (heroItem.promptIdx + 1) % heroItem.prompts.length
                        heroItem.targetText = heroItem.prompts[heroItem.promptIdx]
                        heroItem.typeState = "typing"
                        interval = 80
                    }
                }
            }

            // Text display
            Row {
                anchors.centerIn: parent
                spacing: 0

                Text {
                    text: heroItem.displayText
                    color: root.textPrimary
                    font.pixelSize: 32
                    font.bold: true
                    verticalAlignment: Text.AlignVCenter
                }

                // Blinking cursor
                Text {
                    text: "|"
                    color: theme ? theme.accent : "#7c3aed"
                    font.pixelSize: 32
                    font.bold: true
                    opacity: heroItem.cursorOn ? 1.0 : 0.0
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        // ── HERO → CARDS GAP ──────────────────────────────────────────────────
        Item { Layout.preferredHeight: 32 }

        // ── 4 ACTION CARDS ────────────────────────────────────────────────────
        Item {
            Layout.fillWidth: true
            height: 172

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter:   parent.verticalCenter
                spacing: 16

                QuickCard { cardIcon: "⬆"; cardLabel: "Import Music";  onCardTapped: backend.importDashAudio() }
                QuickCard { cardIcon: "🕐"; cardLabel: "Open Recent";   onCardTapped: root.recentOpen = true }
                QuickCard { cardIcon: "📄"; cardLabel: "From Scratch";  onCardTapped: backend.openProject("") }
                QuickCard { cardIcon: "✨"; cardLabel: "Build with AI"; featured: true
                    onCardTapped: { backend.openProject(""); backend.setCurrentPage(0) } }
            }
        }

        // ── MID SPACER ────────────────────────────────────────────────────────
        Item { Layout.preferredHeight: 64 }

        // ── PROJECTS CARD ─────────────────────────────────────────────────────
        Item {
            Layout.fillWidth: true
            height: 220

            Rectangle {
                anchors.centerIn: parent
                width: Math.min(parent.width - 40, 968)
                height: 220
                radius: 2
                color: root.cardSurface
                border.color: root.overlayBorder
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 18

                    // ── Left column: My Projects ───────────────────────────────
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 8

                        Text {
                            text: "My Projects"
                            color: root.textPrimary
                            font.pixelSize: 13; font.bold: true
                        }

                        Rectangle {
                            Layout.fillWidth: true; height: 40; radius: 7
                            color: newProjH.hovered ? root.overlayHover : root.overlayNormal
                            border.color: root.overlayBorder; border.width: 1
                            Behavior on color { ColorAnimation { duration: 100 } }
                            Text { anchors.centerIn: parent; text: "📄  New Project from Scratch"; color: root.textPrimary; font.pixelSize: 12 }
                            HoverHandler { id: newProjH }
                            TapHandler   { onTapped: backend.openProject("") }
                        }

                        Text {
                            text: "RECENT"
                            color: root.textMuted
                            font.pixelSize: 9; font.letterSpacing: 1.4; font.bold: true
                        }

                        Repeater {
                            model: {
                                var r = backend.recentProjects()
                                return r.length > 0 ? r.slice(0, 4) : []
                            }
                            Rectangle {
                                Layout.fillWidth: true; height: 28; radius: 5
                                color: recH.hovered ? root.overlayHover : "transparent"
                                Behavior on color { ColorAnimation { duration: 80 } }
                                RowLayout {
                                    anchors.fill: parent; anchors.leftMargin: 6; spacing: 7
                                    Rectangle {
                                        width: 20; height: 16; radius: 3
                                        color: theme ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.22) : Qt.rgba(0.48,0.23,0.93,0.28)
                                        Text { anchors.centerIn: parent; text: "〰"; color: theme ? theme.accent : "#7c3aed"; font.pixelSize: 8 }
                                    }
                                    Text {
                                        text: { var p = modelData.split(/[/\\]/); return p[p.length-1] || modelData }
                                        color: root.textSecondary
                                        font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true
                                    }
                                }
                                HoverHandler { id: recH }
                                TapHandler   { onTapped: backend.openProject(modelData) }
                            }
                        }

                        Text {
                            visible: backend.recentProjects().length === 0
                            text: "No recent projects"
                            color: root.textMuted; font.pixelSize: 11
                        }

                        Item { Layout.fillHeight: true }
                    }

                    // ── Divider ────────────────────────────────────────────────
                    Rectangle {
                        width: 1; Layout.fillHeight: true
                        Layout.topMargin: 8; Layout.bottomMargin: 8
                        color: root.overlayBorder
                    }

                    // ── Right column: Quick Actions ────────────────────────────
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 10

                        Item { Layout.fillHeight: true }

                        Text {
                            text: "QUICK ACTIONS"
                            color: root.textMuted
                            font.pixelSize: 9; font.letterSpacing: 1.4; font.bold: true
                        }

                        Rectangle {
                            Layout.fillWidth: true; height: 40; radius: 7
                            color: impH.hovered ? root.overlayHover : root.overlayNormal
                            border.color: root.overlayBorder; border.width: 1
                            Behavior on color { ColorAnimation { duration: 100 } }
                            Text { anchors.centerIn: parent; text: "⬆  Import Audio"; color: root.textPrimary; font.pixelSize: 12 }
                            HoverHandler { id: impH }
                            TapHandler   { onTapped: backend.importDashAudio() }
                        }

                        Rectangle {
                            Layout.fillWidth: true; height: 40; radius: 7
                            color: openRecH.hovered ? root.overlayHover : root.overlayNormal
                            border.color: root.overlayBorder; border.width: 1
                            Behavior on color { ColorAnimation { duration: 100 } }
                            Text { anchors.centerIn: parent; text: "🕐  Open Recent"; color: root.textPrimary; font.pixelSize: 12 }
                            HoverHandler { id: openRecH }
                            TapHandler   { onTapped: root.recentOpen = true }
                        }

                        Item { Layout.fillHeight: true }
                    }
                }
            }
        }

        // ── FILL ──────────────────────────────────────────────────────────────
        Item { Layout.fillHeight: true }

        // ── BOTTOM BAR ────────────────────────────────────────────────────────
        Rectangle {
            id: bottomBar
            Layout.fillWidth: true
            height: 50
            color: theme ? Qt.rgba(theme.bg.r, theme.bg.g, theme.bg.b, 0.96) : Qt.rgba(0.05,0.03,0.10,0.92)
            border.color: root.panelBorder; border.width: 1

            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; spacing: 12

                Rectangle {
                    height: 34; radius: 6
                    width: acRow.implicitWidth + 20
                    color: aHov.hovered ? root.overlayHover : "transparent"

                    RowLayout {
                        id: acRow
                        anchors.centerIn: parent; spacing: 8
                        Rectangle {
                            width: 24; height: 24; radius: 12
                            color: theme ? theme.accent : "#7c3aed"
                            Text { anchors.centerIn: parent; text: root.displayName.charAt(0); color: "#fff"; font.pixelSize: 11; font.bold: true }
                        }
                        Text {
                            text: "Wavy Labs"
                            color: root.textSecondary; font.pixelSize: 11
                        }
                    }

                    HoverHandler { id: aHov }
                    TapHandler   { onTapped: root.accountOpen = true }
                }

                Item { Layout.fillWidth: true }

                Repeater {
                    model: [
                        { label: "Changelog", url: "https://docs.wavylab.net/changelog" },
                        { label: "Docs",      url: "https://docs.wavylab.net" },
                        { label: "Feedback",  url: "https://github.com/stroland02/Wavy-Labs-Code-Base-/issues" }
                    ]
                    Text {
                        text: modelData.label
                        color: lnkH.hovered ? (theme ? theme.accent : "#7c3aed") : root.textMuted
                        font.pixelSize: 11
                        HoverHandler { id: lnkH }
                        TapHandler   { onTapped: Qt.openUrlExternally(modelData.url) }
                    }
                }
            }
        }
    }

    // ── Overlay backdrop ──────────────────────────────────────────────────────
    MouseArea {
        anchors.fill: parent
        z: 99
        visible: root.accountOpen || root.recentOpen
        onClicked: { root.accountOpen = false; root.recentOpen = false }
    }

    // ── Account info panel ────────────────────────────────────────────────────
    Rectangle {
        id: accountPanel
        z: 100
        visible: root.accountOpen
        x: 14
        y: root.height - height - 50
        width: 272
        height: 248
        radius: 10
        color: root.panelBg
        border.color: root.panelBorder
        border.width: 1

        ColumnLayout {
            anchors { top: parent.top; left: parent.left; right: parent.right; margins: 16 }
            spacing: 10

            RowLayout {
                spacing: 12
                Rectangle {
                    width: 44; height: 44; radius: 22
                    color: theme ? theme.accent : "#7c3aed"
                    Text { anchors.centerIn: parent; text: root.displayName.charAt(0); color: "#fff"; font.pixelSize: 20; font.bold: true }
                }
                ColumnLayout {
                    spacing: 2
                    Text { text: "Wavy Labs"; color: root.textPrimary; font.pixelSize: 13; font.bold: true }
                    Text {
                        text: "Free & Open Source"
                        color: root.textMuted; font.pixelSize: 11
                        elide: Text.ElideRight; Layout.maximumWidth: 172
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: root.panelBorder }

            Text { text: "Resources"; color: root.textPrimary; font.pixelSize: 13; font.bold: true }
            ResLink { rLabel: "Changelog"; rUrl: "https://docs.wavylab.net/changelog" }
            ResLink { rLabel: "Docs";      rUrl: "https://docs.wavylab.net" }
            ResLink { rLabel: "Community"; rUrl: "https://github.com/stroland02/Wavy-Labs-Code-Base-/discussions" }
            ResLink { rLabel: "Feedback";  rUrl: "https://github.com/stroland02/Wavy-Labs-Code-Base-/issues" }
        }
    }

    // ── Recent projects panel ─────────────────────────────────────────────────
    Rectangle {
        id: recentPanel
        z: 100
        visible: root.recentOpen
        anchors.centerIn: parent
        width: 400
        height: Math.max(130, Math.min(360, backend.recentProjects().length * 42 + 72))
        radius: 10
        color: root.panelBg
        border.color: root.panelBorder
        border.width: 1

        ColumnLayout {
            anchors { top: parent.top; left: parent.left; right: parent.right; margins: 16 }
            spacing: 4

            Text {
                text: "Recent Projects"; color: root.textPrimary
                font.pixelSize: 14; font.bold: true; Layout.bottomMargin: 6
            }
            Repeater {
                model: backend.recentProjects().slice(0, 8)
                Rectangle {
                    Layout.fillWidth: true; height: 38; radius: 6
                    color: rpH.hovered ? root.overlayHover : "transparent"
                    Behavior on color { ColorAnimation { duration: 80 } }
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 8; spacing: 8
                        Rectangle {
                            width: 26; height: 22; radius: 4
                            color: theme ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.22) : Qt.rgba(0.18,0.08,0.40,0.50)
                            Text { anchors.centerIn: parent; text: "〰"; color: theme ? theme.accent : "#7c3aed"; font.pixelSize: 10 }
                        }
                        Text {
                            text: { var p = modelData.split(/[/\\]/); return p[p.length-1] || modelData }
                            color: root.textPrimary
                            font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true
                        }
                    }
                    HoverHandler { id: rpH }
                    TapHandler   { onTapped: { root.recentOpen = false; backend.openProject(modelData) } }
                }
            }
            Text {
                visible: backend.recentProjects().length === 0
                text: "No recent projects yet"
                color: root.textMuted; font.pixelSize: 12
                Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 8
            }
        }
    }

    // ── Inline components ─────────────────────────────────────────────────────

    // Stellaris-style card with animated corner brackets
    component QuickCard: Item {
        id: qcSelf
        property string cardIcon: ""
        property string cardLabel: ""
        property bool   featured: false
        signal cardTapped

        width: 230; height: 152

        // Per-instance dark detection (inline components can't access root props directly)
        property bool isDarkCard: theme ? (theme.bg.r + theme.bg.g + theme.bg.b < 1.5) : true

        // Card background from theme
        property color cardBg: {
            if (!theme) return featured ? Qt.rgba(0.22,0.07,0.46,0.90) : (qcH.hovered ? Qt.rgba(0.14,0.09,0.26,0.88) : Qt.rgba(0.08,0.05,0.17,0.76))
            if (featured) {
                if (isDarkCard)
                    return Qt.rgba(theme.accent.r * 0.38, theme.accent.g * 0.12, theme.accent.b * 0.38, 0.92)
                return Qt.rgba(theme.accent.r * 0.12 + theme.surface.r * 0.80, theme.accent.g * 0.05 + theme.surface.g * 0.80, theme.accent.b * 0.05 + theme.surface.b * 0.80, 0.92)
            }
            if (qcH.hovered)
                return Qt.rgba(theme.surface.r * 0.87, theme.surface.g * 0.84, theme.surface.b * 0.84, 0.92)
            return Qt.rgba(theme.surface.r * 0.92, theme.surface.g * 0.90, theme.surface.b * 0.90, 0.78)
        }

        property color cardBorder: featured
            ? Qt.rgba(theme ? theme.accent.r : 0.70, theme ? theme.accent.g : 0.35, theme ? theme.accent.b : 1.0, 0.30)
            : (isDarkCard ? Qt.rgba(1,1,1,0.07) : Qt.rgba(0,0,0,0.08))

        // Bracket animation
        property real  bracketLen: qcH.hovered ? 20 : (featured ? 10 : 5)
        property color bracketColor: qcH.hovered
            ? Qt.rgba(theme ? theme.accent.r : 0.72, theme ? theme.accent.g : 0.52, theme ? theme.accent.b : 1.0, 0.92)
            : (featured
                ? Qt.rgba(theme ? theme.accent.r : 0.70, theme ? theme.accent.g : 0.38, theme ? theme.accent.b : 1.0, 0.68)
                : Qt.rgba(theme ? theme.accent.r * 0.70 : 0.52, theme ? theme.accent.g * 0.55 : 0.38, theme ? theme.accent.b * 0.80 : 0.82, 0.30))

        Behavior on bracketLen   { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
        Behavior on bracketColor { ColorAnimation  { duration: 200 } }
        Behavior on cardBg       { ColorAnimation  { duration: 140 } }

        // ── Card surface ───────────────────────────────────────────────────────
        Rectangle {
            anchors.fill: parent
            radius: 2
            color: qcSelf.cardBg
            border.color: qcSelf.cardBorder
            border.width: 1

            ColumnLayout {
                anchors.centerIn: parent; spacing: 10
                Text { text: qcSelf.cardIcon; font.pixelSize: 30; Layout.alignment: Qt.AlignHCenter }
                Text {
                    text: qcSelf.cardLabel
                    color: theme ? Qt.rgba(theme.fg.r, theme.fg.g, theme.fg.b, qcSelf.featured ? 1.0 : 0.86) : Qt.rgba(1,1,1,0.86)
                    font.pixelSize: 13; font.bold: true; font.letterSpacing: 0.4
                    Layout.alignment: Qt.AlignHCenter
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }

        // ── Corner brackets ────────────────────────────────────────────────────
        Rectangle { x: 0;                         y: 0;                          width: bracketLen; height: 1; color: bracketColor }
        Rectangle { x: 0;                         y: 0;                          width: 1; height: bracketLen; color: bracketColor }
        Rectangle { x: parent.width - bracketLen;  y: 0;                          width: bracketLen; height: 1; color: bracketColor }
        Rectangle { x: parent.width - 1;           y: 0;                          width: 1; height: bracketLen; color: bracketColor }
        Rectangle { x: 0;                         y: parent.height - 1;           width: bracketLen; height: 1; color: bracketColor }
        Rectangle { x: 0;                         y: parent.height - bracketLen;  width: 1; height: bracketLen; color: bracketColor }
        Rectangle { x: parent.width - bracketLen;  y: parent.height - 1;           width: bracketLen; height: 1; color: bracketColor }
        Rectangle { x: parent.width - 1;           y: parent.height - bracketLen;  width: 1; height: bracketLen; color: bracketColor }

        HoverHandler { id: qcH }
        TapHandler   { onTapped: qcSelf.cardTapped() }
    }

    component ResLink: Item {
        id: rlSelf
        property string rLabel: ""
        property string rUrl: ""
        implicitWidth: 230; implicitHeight: 26

        RowLayout {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            spacing: 8
            Text { text: "›"; color: theme ? theme.accent : "#7c3aed"; font.pixelSize: 14 }
            Text {
                text: rlSelf.rLabel
                color: rlH.hovered ? (theme ? theme.accent : "#7c3aed") : (theme ? Qt.rgba(theme.fg.r, theme.fg.g, theme.fg.b, 0.75) : Qt.rgba(1,1,1,0.75))
                font.pixelSize: 12
            }
        }
        HoverHandler { id: rlH }
        TapHandler   { onTapped: Qt.openUrlExternally(rlSelf.rUrl) }
    }
}
