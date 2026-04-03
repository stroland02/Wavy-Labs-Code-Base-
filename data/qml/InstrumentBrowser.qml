import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    color: "transparent"

    readonly property color text_:   theme.fg
    readonly property color dim:     theme.dim
    readonly property color border_: theme.outline
    readonly property color surface: theme.surface
    readonly property color accent:  theme.accent

    // ── State ────────────────────────────────────────────────────────────
    property var    instruments: []
    property int    totalResults: 0
    property bool   hasMore: false
    property bool   searching: false
    property int    currentOffset: 0
    property string searchQuery: ""
    property int    categoryIdx: 0
    property int    sourceIdx: 0

    readonly property var categoryKeys: [
        "", "piano", "chromatic_perc", "organ", "guitar", "bass",
        "strings", "brass", "woodwind", "synth_lead", "synth_pad", "drums", "other"
    ]
    readonly property var categoryLabels: [
        "All", "Piano", "Perc", "Organ", "Guitar", "Bass",
        "Strings", "Brass", "Wind", "Leads", "Pads", "Drums", "Other"
    ]
    readonly property var sourceKeys:  ["", "builtin", "builtin_sample", "gm_soundfont", "external", "vst3_reference"]
    readonly property var sourceLabels: ["All", "Presets", "Samples", "GM SF2", "Packs", "VST3"]

    // ── Packs state ─────────────────────────────────────────────────────
    property var packs: []

    // ── Search function ─────────────────────────────────────────────────
    function doSearch(offset) {
        root.searching = true
        root.currentOffset = offset || 0
        backend.searchInstruments(
            root.searchQuery,
            root.categoryKeys[root.categoryIdx],
            root.sourceKeys[root.sourceIdx],
            root.currentOffset,
            50
        )
    }

    Component.onCompleted: {
        doSearch(0)
        backend.listInstrumentPacks()
    }

    // ── Signal handlers ─────────────────────────────────────────────────
    Connections {
        target: backend

        function onInstrumentSearchResults(items, total, hasMore) {
            root.searching = false
            root.instruments = items
            root.totalResults = total
            root.hasMore = hasMore
        }

        function onInstrumentPacksListed(packs) {
            root.packs = packs
        }

        function onInstrumentPackDownloaded(name, path) {
            backend.listInstrumentPacks()
            doSearch(root.currentOffset)
        }
    }

    Timer {
        id: searchTimer
        interval: 350
        onTriggered: root.doSearch(0)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        // ── Search bar ──────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 34
            radius: 6
            color: Qt.rgba(surface.r, surface.g, surface.b, 0.6)
            border.width: 1
            border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.25)

            RowLayout {
                anchors.fill: parent
                anchors.margins: 4
                spacing: 6

                Text {
                    text: "Search"
                    font.pixelSize: 11
                    color: dim
                    Layout.leftMargin: 4
                }

                TextInput {
                    id: searchInput
                    Layout.fillWidth: true
                    font.pixelSize: 12
                    color: text_
                    clip: true
                    selectByMouse: true
                    onTextChanged: {
                        root.searchQuery = text
                        searchTimer.restart()
                    }
                }

                Text {
                    text: root.totalResults + " results"
                    font.pixelSize: 10
                    color: dim
                    Layout.rightMargin: 6
                }
            }
        }

        // ── Category PillTabBar ─────────────────────────────────────────
        PillTabBar {
            Layout.fillWidth: true
            model: root.categoryLabels
            currentIndex: root.categoryIdx
            onTabChanged: function(idx) {
                root.categoryIdx = idx
                root.doSearch(0)
            }
        }

        // ── Source filter chips ─────────────────────────────────────────
        Row {
            Layout.fillWidth: true
            spacing: 6

            Repeater {
                model: root.sourceLabels

                Rectangle {
                    required property string modelData
                    required property int index
                    width: chipText.implicitWidth + 16
                    height: 24
                    radius: 12
                    color: root.sourceIdx === index
                           ? accent
                           : Qt.rgba(surface.r, surface.g, surface.b, 0.5)
                    border.width: 1
                    border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.3)

                    Text {
                        id: chipText
                        anchors.centerIn: parent
                        text: modelData
                        font.pixelSize: 10
                        color: root.sourceIdx === index ? "#ffffff" : dim
                    }

                    TapHandler {
                        onTapped: {
                            root.sourceIdx = index
                            root.doSearch(0)
                        }
                    }
                }
            }
        }

        // ── Results grid ────────────────────────────────────────────────
        Flickable {
            id: resultsFlick
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: width
            contentHeight: gridCol.height
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.VerticalFlick

            ScrollBar.vertical: ScrollBar {
                policy: resultsFlick.contentHeight > resultsFlick.height
                        ? ScrollBar.AlwaysOn : ScrollBar.AsNeeded
                width: 6
                contentItem: Rectangle {
                    implicitWidth: 6
                    radius: 3
                    color: Qt.rgba(accent.r, accent.g, accent.b, 0.4)
                }
            }

            ColumnLayout {
                id: gridCol
                width: parent.width
                spacing: 6

                // Instrument cards in a 3-col grid
                Grid {
                    columns: 3
                    spacing: 6
                    Layout.fillWidth: true

                    Repeater {
                        model: root.instruments

                        Rectangle {
                            required property var modelData
                            required property int index

                            width: (gridCol.width - 12) / 3
                            height: 100
                            radius: 8
                            color: Qt.rgba(surface.r, surface.g, surface.b, 0.55)
                            border.width: 1
                            border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.2)

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 4

                                // Name
                                Text {
                                    text: modelData.name || ""
                                    font.pixelSize: 11
                                    font.bold: true
                                    color: text_
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }

                                // Plugin + source badges
                                Row {
                                    spacing: 4

                                    Rectangle {
                                        width: pluginLabel.implicitWidth + 8
                                        height: 16
                                        radius: 3
                                        color: Qt.rgba(accent.r, accent.g, accent.b, 0.15)
                                        Text {
                                            id: pluginLabel
                                            anchors.centerIn: parent
                                            text: modelData.plugin || ""
                                            font.pixelSize: 9
                                            color: accent
                                        }
                                    }

                                    Rectangle {
                                        width: sourceLabel.implicitWidth + 8
                                        height: 16
                                        radius: 3
                                        color: {
                                            var s = modelData.source || ""
                                            if (s === "builtin") return Qt.rgba(0.2, 0.7, 0.3, 0.15)
                                            if (s === "builtin_sample") return Qt.rgba(0.3, 0.5, 0.8, 0.15)
                                            if (s === "gm_soundfont") return Qt.rgba(0.8, 0.5, 0.2, 0.15)
                                            if (s === "vst3_reference") return Qt.rgba(0.7, 0.3, 0.7, 0.15)
                                            return Qt.rgba(0.5, 0.5, 0.5, 0.15)
                                        }
                                        Text {
                                            id: sourceLabel
                                            anchors.centerIn: parent
                                            text: {
                                                var s = modelData.source || ""
                                                if (s === "builtin") return "Preset"
                                                if (s === "builtin_sample") return "Sample"
                                                if (s === "gm_soundfont") return "GM"
                                                if (s === "vst3_reference") return "VST3"
                                                if (s === "external") return "Pack"
                                                return s
                                            }
                                            font.pixelSize: 9
                                            color: dim
                                        }
                                    }
                                }

                                // Category
                                Text {
                                    text: modelData.category || ""
                                    font.pixelSize: 9
                                    color: dim
                                }

                                Item { Layout.fillHeight: true }

                                // Use / Install button
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 22
                                    radius: 4
                                    color: {
                                        var s = modelData.source || ""
                                        if (s === "vst3_reference") return Qt.rgba(0.7, 0.3, 0.7, 0.3)
                                        if (modelData.requires_download && !modelData.installed)
                                            return Qt.rgba(accent.r, accent.g, accent.b, 0.2)
                                        return accent
                                    }

                                    Text {
                                        anchors.centerIn: parent
                                        text: {
                                            var s = modelData.source || ""
                                            if (s === "vst3_reference") return "Install from..."
                                            if (modelData.requires_download && !modelData.installed) return "Needs SF2"
                                            return "Use"
                                        }
                                        font.pixelSize: 10
                                        font.bold: true
                                        color: {
                                            var s = modelData.source || ""
                                            if (s === "vst3_reference") return dim
                                            if (modelData.requires_download && !modelData.installed) return dim
                                            return "#ffffff"
                                        }
                                    }

                                    TapHandler {
                                        onTapped: {
                                            var item = modelData
                                            var s = item.source || ""

                                            if (s === "vst3_reference" && item.install_url) {
                                                Qt.openUrlExternally(item.install_url)
                                                return
                                            }

                                            // Use instrument — add track with preset/sample
                                            if (!item.requires_download || item.installed) {
                                                var plugin = item.plugin || "tripleoscillator"
                                                var name = item.name || "Instrument"
                                                var preset = item.preset || ""
                                                var sample = item.sample_path || ""
                                                backend.addInstrumentTrack(plugin, name, preset, sample)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // Load more button
                Rectangle {
                    Layout.fillWidth: true
                    height: 32
                    radius: 6
                    visible: root.hasMore && !root.searching
                    color: Qt.rgba(accent.r, accent.g, accent.b, 0.12)

                    Text {
                        anchors.centerIn: parent
                        text: "Load more..."
                        font.pixelSize: 11
                        color: accent
                    }

                    TapHandler {
                        onTapped: root.doSearch(root.currentOffset + 50)
                    }
                }

                // Searching indicator
                Rectangle {
                    Layout.fillWidth: true
                    height: 32
                    color: "transparent"
                    visible: root.searching

                    Row {
                        anchors.centerIn: parent
                        spacing: 6
                        Repeater {
                            model: 3
                            delegate: Rectangle {
                                width: 6; height: 6; radius: 3
                                color: accent
                                SequentialAnimation on opacity {
                                    loops: Animation.Infinite; running: true
                                    PauseAnimation { duration: index * 180 }
                                    NumberAnimation { to: 1.0; duration: 250 }
                                    NumberAnimation { to: 0.2; duration: 250 }
                                    PauseAnimation { duration: (2 - index) * 180 }
                                }
                            }
                        }
                    }
                }

                // ── Pack Manager ────────────────────────────────────────
                Rectangle {
                    Layout.fillWidth: true
                    Layout.topMargin: 12
                    height: packCol.height + 24
                    radius: 10
                    color: Qt.rgba(surface.r, surface.g, surface.b, 0.55)
                    border.width: 1
                    border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.2)
                    visible: root.packs.length > 0

                    ColumnLayout {
                        id: packCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 12
                        spacing: 8

                        Text {
                            text: "Downloadable Packs"
                            font.pixelSize: 13
                            font.bold: true
                            color: text_
                        }

                        Repeater {
                            model: root.packs

                            Rectangle {
                                required property var modelData
                                required property int index
                                Layout.fillWidth: true
                                height: 54
                                radius: 6
                                color: Qt.rgba(surface.r, surface.g, surface.b, 0.3)

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 8
                                    spacing: 8

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2
                                        Text {
                                            text: modelData.name || ""
                                            font.pixelSize: 11
                                            font.bold: true
                                            color: text_
                                        }
                                        Text {
                                            text: (modelData.description || "") + " (" + (modelData.size_mb || 0) + " MB, " + (modelData.license || "") + ")"
                                            font.pixelSize: 9
                                            color: dim
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                    }

                                    Rectangle {
                                        width: dlBtnText.implicitWidth + 16
                                        height: 26
                                        radius: 4
                                        color: modelData.installed ? Qt.rgba(0.2, 0.7, 0.3, 0.3) : accent

                                        Text {
                                            id: dlBtnText
                                            anchors.centerIn: parent
                                            text: modelData.installed ? "Installed" : "Download"
                                            font.pixelSize: 10
                                            font.bold: true
                                            color: modelData.installed ? Qt.rgba(0.2, 0.7, 0.3, 1.0) : "#ffffff"
                                        }

                                        TapHandler {
                                            onTapped: {
                                                if (!modelData.installed) {
                                                    backend.downloadInstrumentPack(modelData.name)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Item { height: 20 }
            }
        }
    }
}
