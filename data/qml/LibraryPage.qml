import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    color: theme.bg

    readonly property color text_:   theme.fg
    readonly property color dim:     theme.dim
    readonly property color border_: theme.outline
    readonly property color surface: theme.surface
    readonly property color accent:  theme.accent

    // ── Library mode toggle ─────────────────────────────────────────────
    property string libraryMode: "midi_audio"  // "midi_audio" | "instruments"

    // ── View state ─────────────────────────────────────────────────────────
    property string viewState: "databases"   // "databases" | "browse"

    // ── Active database + filter state ─────────────────────────────────────
    property var    activeDb:      null    // selected database object
    property var    activeFilters:    ({})   // {dimId: selectedOption}  radio per dim
    property int    selectedGenreIdx: 0    // 0 = All; index into genreConfig
    property string browseDb:        ""    // db name for RPC
    property string browseQuery:   ""      // last composed query sent to RPC

    // ── Browse results ──────────────────────────────────────────────────────
    property var  browseResults: []
    property int  browseTotal:   0
    property bool browseHasMore: false
    property bool browsing:      false

    // ── Database definitions ────────────────────────────────────────────────
    readonly property var databases: [
        {
            db:    "MidiWorld",
            label: "MidiWorld",
            type:  "MIDI",
            color: "#42a5f5",
            desc:  "Genre MIDI — pop, jazz, rock, R&B, blues. Direct import, no sign-in.",
            count: "1000s of files",
            filterDims: [
                {
                    id: "genre", label: "Genre",
                    opts: ["pop","jazz","rock","hip-hop","blues","country",
                           "dance","classical","punk","rap"]
                }
            ]
        },
        {
            db:    "Groove MIDI",
            label: "Groove MIDI",
            type:  "DRUMS",
            color: "#ff8a65",
            desc:  "1,150 human-performed drum patterns by professional drummers",
            count: "1.1k files",
            filterDims: [
                {
                    id: "style", label: "Style",
                    opts: ["jazz","funk","hiphop","pop","rock","soul","afrobeat",
                           "latin","country","reggae"]
                },
                {
                    id: "type", label: "Type",
                    opts: ["beat","fill"]
                }
            ]
        },
        {
            db:    "ldrolez Chords",
            label: "ldrolez Chords",
            type:  "CHORDS",
            color: "#ab47bc",
            desc:  "2,000+ chord progressions by style and mood",
            count: "2k+ files",
            filterDims: [
                {
                    id: "style", label: "Style",
                    opts: ["trap","soul","house","pop","jazz"]
                }
            ]
        },
        {
            db:    "HookTheory",
            label: "HookTheory",
            type:  "CHORDS",
            color: "#ef5350",
            desc:  "Music-theory chord progressions from roman numeral analysis",
            count: "Generated",
            filterDims: [
                {
                    id: "genre", label: "Genre",
                    opts: ["trap","rnb","house","jazz","pop","drill"]
                }
            ]
        },
        {
            db:    "WaivOps Drums",
            label: "WaivOps Drums",
            type:  "DRUMS",
            color: "#ffa726",
            desc:  "CC-licensed MIDI drum patterns — trap 808s, house kicks",
            count: "300+ files",
            filterDims: [
                {
                    id: "genre", label: "Genre",
                    opts: ["trap","house","808"]
                }
            ]
        },
        {
            db:    "BitMidi",
            label: "BitMidi",
            type:  "MIDI",
            color: "#78909c",
            desc:  "General MIDI collection — strongest for jazz and classical",
            count: "100k+ files",
            filterDims: []
        },
        {
            db:    "Jamendo",
            label: "Jamendo",
            type:  "AUDIO",
            color: "#66bb6a",
            desc:  "600k+ CC-licensed tracks — genre, mood, BPM. Free to import.",
            count: "600k tracks",
            filterDims: [
                {
                    id: "genre", label: "Genre",
                    opts: ["electronic","pop","jazz","hiphop","rock","rnb","ambient",
                           "classical","folk","metal","reggae","house","lofi",
                           "funk","soul","trap"]
                }
            ]
        },
        {
            db:    "Freesound",
            label: "Freesound",
            type:  "AUDIO",
            color: "#26c6da",
            desc:  "500k CC sound effects, loops, and one-shots. Direct import.",
            count: "500k sounds",
            filterDims: [
                {
                    id: "genre", label: "Type",
                    opts: ["loop","beat","sample","bass","pad","synth",
                           "drum","vocal","sfx","texture","ambient"]
                }
            ]
        },
        {
            db:    "SoundCloud",
            label: "SoundCloud",
            type:  "AUDIO",
            color: "#ff5500",
            desc:  "Search and import SoundCloud tracks. Auto-authenticated.",
            count: "200M+ tracks",
            filterDims: [
                {
                    id: "genre", label: "Genre",
                    opts: ["trap","drill","house","techno","jazz","rnb","soul",
                           "funk","pop","rock","lofi","ambient","classical"]
                }
            ]
        }
    ]

    // ── Genre filter config — each entry defines which DBs are shown + pre-filter
    readonly property var genreConfig: [
        { label: "All",          dbs: null,
          preFilter: {} },
        { label: "Pop",          dbs: ["MidiWorld","HookTheory","ldrolez Chords","Jamendo"],
          preFilter: { genre: "pop" } },
        { label: "Jazz",         dbs: ["MidiWorld","BitMidi","Groove MIDI"],
          preFilter: { genre: "jazz" } },
        { label: "R\u0026B",     dbs: ["MidiWorld","HookTheory","ldrolez Chords","Jamendo"],
          preFilter: { genre: "hip-hop" } },
        { label: "Rock",         dbs: ["MidiWorld","BitMidi"],
          preFilter: { genre: "rock" } },
        { label: "Blues",        dbs: ["MidiWorld","BitMidi"],
          preFilter: { genre: "blues" } },
        { label: "Drums",        dbs: ["Groove MIDI","WaivOps Drums"],
          preFilter: {} },
        { label: "Chords",       dbs: ["ldrolez Chords","HookTheory"],
          preFilter: {} }
    ]

    // ── Derived: which databases to show for the selected genre tab ─────────
    readonly property var filteredDatabases: {
        var cfg = root.genreConfig[root.selectedGenreIdx]
        if (!cfg || !cfg.dbs) return root.databases
        var allowed = cfg.dbs
        return root.databases.filter(function(db) {
            return allowed.indexOf(db.db) !== -1
        })
    }

    // ── Helper functions ────────────────────────────────────────────────────

    function findDb(dbName) {
        for (var i = 0; i < databases.length; i++) {
            if (databases[i].db === dbName) return databases[i]
        }
        return null
    }

    function buildQuery() {
        var parts = []
        for (var k in root.activeFilters) {
            if (root.activeFilters[k]) parts.push(root.activeFilters[k])
        }
        var t = browseSearchField.text.trim()
        if (t) parts.push(t)
        return parts.join(" ")
    }

    function openDatabase(dbObj, preFilters) {
        root.activeDb      = dbObj
        root.activeFilters = preFilters || {}
        root.browseDb      = dbObj.db
        root.browseResults = []
        root.browseTotal   = 0
        root.browseHasMore = false
        root.viewState     = "browse"
        browseSearchField.text = ""
        root.browsing = true
        var q = root.buildQuery()
        root.browseQuery = q
        backend.browseDataset(dbObj.db, q, 0)
    }

    function openDatabaseByName(dbName, preFilters) {
        var db = findDb(dbName)
        if (db) openDatabase(db, preFilters || {})
    }

    function applyFilter(dimId, opt) {
        var f = Object.assign({}, root.activeFilters)
        f[dimId] = (f[dimId] === opt) ? "" : opt    // toggle radio
        root.activeFilters = f
        root.browseResults = []
        root.browsing = true
        var q = root.buildQuery()
        root.browseQuery = q
        backend.browseDataset(root.browseDb, q, 0)
    }

    function buildPills(item) {
        var p = []
        if (item.genre && item.genre !== "")  p.push(item.genre)
        if (item.bpm   && item.bpm > 0)       p.push(Math.round(item.bpm) + " BPM")
        if (item.key   && item.key   !== "")  p.push(item.key)
        return p
    }

    // ── Backend signal connections ──────────────────────────────────────────
    Connections {
        target: backend

        function onActiveGenreChanged(genre) {
            if (!genre || genre === "") { root.selectedGenreIdx = 0; return }
            var g = genre.toLowerCase()
            // Map active genre → genreConfig tab index (just filters the grid)
            if (g === "trap" || g === "rage trap" || g === "pop trap"
                    || g === "uk drill" || g === "drill") {
                // no dedicated tab — leave as All
                root.selectedGenreIdx = 0
            } else if (g === "jazz") {
                root.selectedGenreIdx = 2   // Jazz
            } else if (g === "rnb" || g === "r&b" || g === "neo soul" || g === "neo-soul") {
                root.selectedGenreIdx = 3   // R&B
            } else if (g === "rock") {
                root.selectedGenreIdx = 4   // Rock
            } else if (g === "blues" || g === "soul" || g === "funk") {
                root.selectedGenreIdx = 5   // Blues
            } else if (g === "pop" || g === "lofi" || g === "lo-fi" || g === "future bass") {
                root.selectedGenreIdx = 1   // Pop
            } else if (g === "house" || g === "big room") {
                root.selectedGenreIdx = 0   // All (no House tab)
            } else {
                root.selectedGenreIdx = 0
            }
        }

        function onDatasetBrowseReady(items, total, hasMore, append) {
            if (append)
                root.browseResults = root.browseResults.concat(Array.from(items))
            else
                root.browseResults = Array.from(items)
            root.browseTotal   = total
            root.browseHasMore = hasMore
            root.browsing      = false
        }

        function onMidicapsStatusUpdate(status, progress, filesExtracted,
                                        bytesDownloaded, totalBytes) {
            // MidiCaps is on-demand — no archive download needed
        }
    }

    // ── Debounce timer for search field ─────────────────────────────────────
    Timer {
        id: searchTimer
        interval: 400
        onTriggered: {
            root.browseResults = []
            root.browsing = true
            var q = root.buildQuery()
            root.browseQuery = q
            backend.browseDataset(root.browseDb, q, 0)
        }
    }

    // ══════════════════════════════════════════════════════════════════════
    // MODE TOGGLE — MIDI/Audio vs Instruments
    // ══════════════════════════════════════════════════════════════════════
    Row {
        id: modeToggle
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: 12
        spacing: 0
        z: 10
        height: 30

        Repeater {
            model: ["MIDI / Audio", "Instruments"]
            delegate: Rectangle {
                required property string modelData
                required property int index
                width: modeToggle.width / 2
                height: 30
                radius: index === 0 ? 6 : 6
                color: (index === 0 ? root.libraryMode === "midi_audio" : root.libraryMode === "instruments")
                       ? accent
                       : Qt.rgba(surface.r, surface.g, surface.b, 0.5)
                border.width: 1
                border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.3)

                Text {
                    anchors.centerIn: parent
                    text: modelData
                    font.pixelSize: 11
                    font.bold: true
                    color: (index === 0 ? root.libraryMode === "midi_audio" : root.libraryMode === "instruments")
                           ? "#ffffff" : dim
                }

                TapHandler {
                    onTapped: root.libraryMode = (index === 0) ? "midi_audio" : "instruments"
                }
            }
        }
    }

    // ══════════════════════════════════════════════════════════════════════
    // INSTRUMENT BROWSER (Loader — only active when mode is "instruments")
    // ══════════════════════════════════════════════════════════════════════
    Loader {
        id: instrBrowserLoader
        anchors.fill: parent
        anchors.topMargin: modeToggle.height + 20
        anchors.margins: 12
        active: root.libraryMode === "instruments"
        source: "qrc:/wavy/qml/InstrumentBrowser.qml"
    }

    // ══════════════════════════════════════════════════════════════════════
    // DATABASES GRID VIEW
    // ══════════════════════════════════════════════════════════════════════
    ColumnLayout {
        id: dbView
        anchors.fill: parent
        anchors.topMargin: modeToggle.height + 20
        anchors.margins: 12
        spacing: 10
        visible: root.viewState === "databases" && root.libraryMode === "midi_audio"

        Text {
            text: "Libraries"
            font.pixelSize: 13
            font.weight: Font.Medium
            color: dim
        }

        // ── Quick-access genre tab bar (PillTabBar style) ──────────────────
        PillTabBar {
            id: genreBar
            Layout.fillWidth: true
            model: root.genreConfig.map(function(c) { return c.label })
            currentIndex: root.selectedGenreIdx
            accentColor: accent
            onTabChanged: function(idx) { root.selectedGenreIdx = idx }
        }

        // ── Database cards grid ─────────────────────────────────────────
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true

            GridLayout {
                width: parent.width
                columns: 2
                columnSpacing: 10
                rowSpacing: 10

                Repeater {
                    model: root.filteredDatabases

                    delegate: Rectangle {
                        id: dbCard
                        Layout.fillWidth: true
                        implicitHeight: 96
                        radius: 10
                        clip: true

                        property bool isLocked: modelData.requiresKey === true

                        color: dbCardMouse.containsMouse && !isLocked
                            ? Qt.lighter(surface, 1.08)
                            : surface
                        border.color: border_
                        border.width: 1

                        // Left accent color strip
                        Rectangle {
                            width: 4
                            height: parent.height
                            color: modelData.color
                        }

                        // Lock icon for credential-required databases
                        Text {
                            visible: dbCard.isLocked
                            text: "\uD83D\uDD12"
                            font.pixelSize: 13
                            anchors.top: parent.top
                            anchors.right: parent.right
                            anchors.topMargin: 6
                            anchors.rightMargin: 8
                        }

                        // Type badge (top-right, behind lock if locked)
                        Rectangle {
                            visible: !dbCard.isLocked
                            radius: 4
                            color: "transparent"
                            border.color: modelData.color
                            border.width: 1
                            implicitWidth: typeBadge.implicitWidth + 12
                            implicitHeight: 18
                            anchors.top: parent.top
                            anchors.right: parent.right
                            anchors.topMargin: 8
                            anchors.rightMargin: 8

                            Text {
                                id: typeBadge
                                text: modelData.type
                                color: modelData.color
                                font.pixelSize: 10
                                font.weight: Font.Medium
                                anchors.centerIn: parent
                            }
                        }

                        // Card content
                        ColumnLayout {
                            anchors.top: parent.top
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.topMargin: 10
                            anchors.leftMargin: 16
                            anchors.rightMargin: 10
                            spacing: 3

                            Text {
                                text: modelData.label
                                font.pixelSize: 13
                                font.weight: Font.Bold
                                color: dbCard.isLocked ? dim : text_
                            }

                            Text {
                                text: modelData.count
                                font.pixelSize: 10
                                color: modelData.color
                                visible: !dbCard.isLocked
                            }

                            Text {
                                text: modelData.desc
                                font.pixelSize: 10
                                color: dim
                                wrapMode: Text.Wrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }

                            // "Setup →" link for locked databases
                            Text {
                                visible: dbCard.isLocked
                                text: "Setup \u2192"
                                font.pixelSize: 10
                                color: accent

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: Qt.openUrlExternally(modelData.keyUrl || "")
                                }
                            }
                        }

                        MouseArea {
                            id: dbCardMouse
                            anchors.fill: parent
                            cursorShape: dbCard.isLocked ? Qt.ArrowCursor : Qt.PointingHandCursor
                            hoverEnabled: true
                            onClicked: {
                                if (!dbCard.isLocked) {
                                    var cfg = root.genreConfig[root.selectedGenreIdx]
                                    var preFilters = {}
                                    if (cfg && cfg.preFilter && modelData.filterDims) {
                                        for (var i = 0; i < modelData.filterDims.length; i++) {
                                            if (modelData.filterDims[i].id === "genre") {
                                                preFilters = cfg.preFilter
                                                break
                                            }
                                        }
                                    }
                                    root.openDatabase(modelData, preFilters)
                                } else {
                                    Qt.openUrlExternally(modelData.keyUrl || "")
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ══════════════════════════════════════════════════════════════════════
    // BROWSE VIEW
    // ══════════════════════════════════════════════════════════════════════
    ColumnLayout {
        id: browseView
        anchors.fill: parent
        anchors.topMargin: modeToggle.height + 20
        anchors.margins: 12
        spacing: 8
        visible: root.viewState === "browse" && root.libraryMode === "midi_audio"

        // ── Header: back + db name + total ───────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Rectangle {
                implicitWidth: backLabel.implicitWidth + 20
                implicitHeight: 28
                radius: 5
                color: Qt.rgba(theme.fg.r, theme.fg.g, theme.fg.b, 0.06)
                border.color: border_
                border.width: 1

                Text {
                    id: backLabel
                    text: "\u2190 Back"
                    color: text_
                    font.pixelSize: 12
                    anchors.centerIn: parent
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        searchTimer.stop()
                        root.viewState    = "databases"
                        root.browseResults = []
                        root.browseQuery  = ""
                        root.browsing     = false
                        root.activeDb     = null
                        root.activeFilters = ({})
                    }
                }
            }

            // DB name (accent-colored)
            Text {
                text: root.activeDb ? root.activeDb.label : ""
                font.pixelSize: 14
                font.weight: Font.Bold
                color: root.activeDb ? root.activeDb.color : text_
            }

            Item { Layout.fillWidth: true }

            Text {
                visible: root.browseTotal > 0
                text: root.browseTotal.toLocaleString() + " files"
                font.pixelSize: 11
                color: dim
            }
        }

        // ── Per-database filter chip rows ────────────────────────────────
        // One row per filterDim — radio selection per dim
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: root.activeDb !== null
                     && root.activeDb.filterDims !== undefined
                     && root.activeDb.filterDims.length > 0

            Repeater {
                model: root.activeDb ? root.activeDb.filterDims : []

                delegate: ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    property var dim: modelData

                    // Dim label (e.g. "Genre:", "Style:", "Type:")
                    Text {
                        text: dim.label + ":"
                        font.pixelSize: 10
                        color: dim_
                        property color dim_: root.dim
                    }

                    // Horizontally scrollable chip row
                    Flickable {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 30
                        contentWidth: filterChipRow.implicitWidth
                        contentHeight: 30
                        clip: true
                        flickableDirection: Flickable.HorizontalFlick

                        Row {
                            id: filterChipRow
                            spacing: 5
                            height: 30

                            Repeater {
                                model: dim.opts

                                delegate: Rectangle {
                                    property string optValue: modelData
                                    property string dimId:    dim.id
                                    property bool   isActive: (root.activeFilters[dimId] || "") === optValue

                                    height: 24
                                    anchors.verticalCenter: parent ? parent.verticalCenter : undefined
                                    implicitWidth: filterChipTxt.implicitWidth + 16
                                    radius: 12

                                    color: isActive
                                        ? root.activeDb.color
                                        : Qt.rgba(root.surface.r, root.surface.g, root.surface.b, 0.5)
                                    border.color: isActive
                                        ? root.activeDb.color
                                        : root.border_
                                    border.width: 1

                                    Text {
                                        id: filterChipTxt
                                        text: optValue
                                        font.pixelSize: 10
                                        font.weight: isActive ? Font.Medium : Font.Normal
                                        color: isActive ? "white" : root.dim
                                        anchors.centerIn: parent
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.applyFilter(dimId, optValue)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // ── Search field ─────────────────────────────────────────────────
        TextField {
            id: browseSearchField
            Layout.fillWidth: true
            placeholderText: "Search by genre, mood, or title\u2026"
            placeholderTextColor: dim
            color: text_
            font.pixelSize: 12
            leftPadding: 10
            rightPadding: 10
            topPadding: 6
            bottomPadding: 6

            onTextChanged: {
                searchTimer.restart()
            }

            Keys.onEscapePressed: {
                text = ""
                focus = false
            }

            background: Rectangle {
                color: Qt.rgba(theme.fg.r, theme.fg.g, theme.fg.b, 0.06)
                radius: 6
                border.color: border_
                border.width: 1
            }
        }

        // ── Setup card for locked databases ──────────────────────────────
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.activeDb !== null
                     && root.activeDb.requiresKey === true
                     && !root.browsing
                     && root.browseResults.length === 0

            Rectangle {
                anchors.centerIn: parent
                width: Math.min(parent.width - 32, 260)
                height: setupCol.implicitHeight + 32
                radius: 12
                color: surface
                border.color: border_
                border.width: 1

                ColumnLayout {
                    id: setupCol
                    anchors.centerIn: parent
                    width: parent.width - 32
                    spacing: 8

                    Text {
                        text: "\uD83D\uDD12"
                        font.pixelSize: 28
                        Layout.alignment: Qt.AlignHCenter
                    }

                    Text {
                        text: root.activeDb ? root.activeDb.label + " requires an API key" : ""
                        font.pixelSize: 12
                        font.weight: Font.Medium
                        color: text_
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                    }

                    Text {
                        text: root.activeDb
                              ? "Add " + (root.activeDb.keyName || "") + " to wavy-ai/.env"
                              : ""
                        font.pixelSize: 10
                        color: dim
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                    }

                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        implicitWidth: getKeyLabel.implicitWidth + 24
                        implicitHeight: 30
                        radius: 6
                        color: Qt.rgba(accent.r, accent.g, accent.b, 0.18)
                        border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.6)
                        border.width: 1

                        Text {
                            id: getKeyLabel
                            text: "Get API Key \u2192"
                            color: accent
                            font.pixelSize: 11
                            anchors.centerIn: parent
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (root.activeDb && root.activeDb.keyUrl)
                                    Qt.openUrlExternally(root.activeDb.keyUrl)
                            }
                        }
                    }
                }
            }
        }

        // ── Loading spinner (empty + loading) ─────────────────────────────
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.browsing && root.browseResults.length === 0
                     && (root.activeDb === null || root.activeDb.requiresKey !== true)

            Row {
                anchors.centerIn: parent
                spacing: 8

                Repeater {
                    model: 3
                    delegate: Rectangle {
                        width: 8
                        height: 8
                        radius: 4
                        color: accent

                        SequentialAnimation on opacity {
                            loops: Animation.Infinite
                            running: true
                            PauseAnimation { duration: index * 200 }
                            NumberAnimation { to: 1.0; duration: 300 }
                            NumberAnimation { to: 0.25; duration: 300 }
                            PauseAnimation { duration: (2 - index) * 200 }
                        }
                    }
                }
            }
        }

        // ── Empty state (no results, not loading, not locked) ─────────────
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !root.browsing
                     && root.browseResults.length === 0
                     && root.browseQuery !== ""
                     && (root.activeDb === null || root.activeDb.requiresKey !== true)

            Text {
                anchors.centerIn: parent
                text: "No results for \u201c" + root.browseQuery + "\u201d"
                font.pixelSize: 13
                color: dim
            }
        }

        // ── Results list ──────────────────────────────────────────────────
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth
            visible: root.browseResults.length > 0

            ColumnLayout {
                width: parent.width
                spacing: 8

                Repeater {
                    model: root.browseResults

                    delegate: Rectangle {
                        id: resultRow
                        Layout.fillWidth: true
                        implicitHeight: itemCol.implicitHeight + 20
                        radius: 8
                        color: surface
                        border.color: border_
                        border.width: 1

                        property var itemData: modelData

                        ColumnLayout {
                            id: itemCol
                            anchors.top: parent.top
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.margins: 10
                            spacing: 4

                            // Title row + import button
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                Text {
                                    text: resultRow.itemData.title || ""
                                    font.pixelSize: 13
                                    font.weight: Font.SemiBold
                                    color: text_
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }

                                Rectangle {
                                    property bool canDownload:
                                        resultRow.itemData._download_available !== false

                                    implicitWidth: importBtnText.implicitWidth + 16
                                    implicitHeight: 24
                                    radius: 4
                                    color: canDownload
                                        ? Qt.rgba(0.2, 0.6, 1.0, 0.18)
                                        : Qt.rgba(0.5, 0.5, 0.5, 0.10)
                                    border.color: canDownload
                                        ? Qt.rgba(0.2, 0.6, 1.0, 0.5)
                                        : Qt.rgba(0.5, 0.5, 0.5, 0.3)
                                    border.width: 1

                                    Text {
                                        id: importBtnText
                                        text: resultRow.itemData._download_available !== false
                                              ? "Import \u2193" : "Preview"
                                        color: resultRow.itemData._download_available !== false
                                               ? "#64b5f6" : dim
                                        font.pixelSize: 11
                                        anchors.centerIn: parent
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: parent.canDownload
                                            ? Qt.PointingHandCursor : Qt.ArrowCursor
                                        onClicked: {
                                            if (!parent.canDownload) return
                                            backend.downloadLibraryFile(
                                                root.browseDb,
                                                resultRow.itemData.file_id || "",
                                                resultRow.itemData.title   || "Imported File",
                                                resultRow.itemData.plugin  || ""
                                            )
                                        }
                                    }
                                }
                            }

                            // Subtitle (instrument list, artist, genre tags)
                            Text {
                                text: resultRow.itemData.subtitle || ""
                                font.pixelSize: 10
                                color: accent
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                                visible: (resultRow.itemData.subtitle || "") !== ""
                            }

                            // Caption
                            Text {
                                text: resultRow.itemData.caption || ""
                                font.pixelSize: 11
                                color: dim
                                wrapMode: Text.Wrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                                visible: (resultRow.itemData.caption || "") !== ""
                            }

                            // Metadata pills
                            Row {
                                spacing: 5
                                visible: buildPills(resultRow.itemData).length > 0

                                Repeater {
                                    model: buildPills(resultRow.itemData)
                                    delegate: Rectangle {
                                        radius: 9
                                        color: Qt.rgba(theme.fg.r, theme.fg.g, theme.fg.b, 0.07)
                                        implicitWidth: pillTxt.implicitWidth + 10
                                        implicitHeight: 18

                                        Text {
                                            id: pillTxt
                                            text: modelData
                                            font.pixelSize: 10
                                            color: dim
                                            anchors.centerIn: parent
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // "Load more" footer
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 36
                    radius: 8
                    color: Qt.rgba(theme.fg.r, theme.fg.g, theme.fg.b, 0.04)
                    border.color: border_
                    border.width: 1
                    visible: root.browseHasMore && !root.browsing

                    Text {
                        anchors.centerIn: parent
                        text: "Load 20 more  \u00b7  " + root.browseTotal.toLocaleString() + " total"
                        font.pixelSize: 11
                        color: dim
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.browsing = true
                            backend.browseDataset(
                                root.browseDb,
                                root.browseQuery,
                                root.browseResults.length
                            )
                        }
                    }
                }

                // Inline loading spinner for "load more"
                Item {
                    Layout.fillWidth: true
                    implicitHeight: 32
                    visible: root.browsing && root.browseResults.length > 0

                    Row {
                        anchors.centerIn: parent
                        spacing: 6

                        Repeater {
                            model: 3
                            delegate: Rectangle {
                                width: 6
                                height: 6
                                radius: 3
                                color: accent

                                SequentialAnimation on opacity {
                                    loops: Animation.Infinite
                                    running: true
                                    PauseAnimation { duration: index * 180 }
                                    NumberAnimation { to: 1.0; duration: 250 }
                                    NumberAnimation { to: 0.2; duration: 250 }
                                    PauseAnimation { duration: (2 - index) * 180 }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
