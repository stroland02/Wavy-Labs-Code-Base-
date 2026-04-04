#include "GenreConfigPopup.h"
#include "../QML/AIBackend.h"
#include "../QML/GenreModes.h"
#include "../ThemeManager/ThemeManager.h"

#include <QApplication>
#include <QElapsedTimer>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QInputDialog>
#include <QPainter>
#include <QPainterPath>
#include <QScreen>
#include <QSettings>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

// ---------------------------------------------------------------------------
// GenreConfigPopup
// ---------------------------------------------------------------------------

GenreConfigPopup::GenreConfigPopup(AIBackend* backend, QWidget* parent)
    : QWidget(parent, Qt::Popup | Qt::FramelessWindowHint)
    , m_backend(backend)
{
    setFixedWidth(370);
    buildUI();
    applyThemeColors();

    connect(Wavy::ThemeManager::themeObject(), &Wavy::WavyTheme::changed,
            this, &GenreConfigPopup::applyThemeColors);
}

// ---------------------------------------------------------------------------
// paintEvent — rounded rect with themed surface color
// ---------------------------------------------------------------------------

void GenreConfigPopup::paintEvent(QPaintEvent*)
{
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);

    auto* th = Wavy::ThemeManager::themeObject();
    const QColor surface = th ? th->surface() : QColor("#2a2a2a");
    const QColor accent  = th ? th->accent()  : QColor("#00e87a");

    // Solid surface fill
    QColor borderCol(
        qMin(255, int(accent.red()   * 0.35)),
        qMin(255, int(accent.green() * 0.35)),
        qMin(255, int(accent.blue()  * 0.35)));

    p.setBrush(surface);
    p.setPen(QPen(borderCol, 1));
    p.drawRoundedRect(QRectF(rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6);
}

// ---------------------------------------------------------------------------
// showBelow — position below anchor, clamp to screen
// ---------------------------------------------------------------------------

void GenreConfigPopup::showBelow(QWidget* anchor)
{
    if (!anchor) return;

    // Ensure layout is computed before positioning
    adjustSize();

    QPoint anchorGlobal = anchor->mapToGlobal(QPoint(0, anchor->height() + 4));

    const QScreen* screen = QApplication::screenAt(anchor->mapToGlobal(QPoint(0,0)));
    if (!screen) screen = QApplication::primaryScreen();

    QPoint pos = anchorGlobal;
    if (screen) {
        const QRect avail = screen->availableGeometry();
        if (pos.x() + width() > avail.right())
            pos.setX(avail.right() - width());
        if (pos.y() + height() > avail.bottom())
            pos.setY(anchor->mapToGlobal(QPoint(0, 0)).y() - height() - 4);
        if (pos.x() < avail.left())
            pos.setX(avail.left());
        if (pos.y() < avail.top())
            pos.setY(avail.top());
    }

    move(pos);
    show();
    raise();
}

// ---------------------------------------------------------------------------
// buildUI
// ---------------------------------------------------------------------------

void GenreConfigPopup::buildUI()
{
    auto* outerLayout = new QVBoxLayout(this);
    outerLayout->setContentsMargins(12, 12, 12, 12);
    outerLayout->setSpacing(0);

    // Header
    m_headerLabel = new QLabel(QStringLiteral("GENRE SETTINGS"), this);
    m_headerLabel->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    outerLayout->addWidget(m_headerLabel);
    outerLayout->addSpacing(8);

    // Scroll area
    m_scrollArea = new QScrollArea(this);
    m_scrollArea->setWidgetResizable(true);
    m_scrollArea->setFrameShape(QFrame::NoFrame);
    m_scrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_scrollArea->setMaximumHeight(520);

    auto* scrollContent = new QWidget;
    auto* contentLayout = new QVBoxLayout(scrollContent);
    contentLayout->setContentsMargins(0, 0, 4, 0);
    contentLayout->setSpacing(6);

    // ── Production section ────────────────────────────────────────────────
    m_prodLabel = new QLabel(QStringLiteral("Production"), scrollContent);
    contentLayout->addWidget(m_prodLabel);

    auto* prodGrid = new QGridLayout;
    prodGrid->setContentsMargins(0, 0, 0, 0);
    prodGrid->setHorizontalSpacing(8);
    prodGrid->setVerticalSpacing(4);

    // BPM
    prodGrid->addWidget(new QLabel("BPM", scrollContent), 0, 0);
    m_bpmSpin = new QSpinBox(scrollContent);
    m_bpmSpin->setRange(10, 999);
    m_bpmSpin->setValue(120);
    prodGrid->addWidget(m_bpmSpin, 0, 1);

    // Time Signature
    prodGrid->addWidget(new QLabel("Time Sig", scrollContent), 1, 0);
    auto* tsWidget = new QWidget(scrollContent);
    auto* tsLayout = new QHBoxLayout(tsWidget);
    tsLayout->setContentsMargins(0, 0, 0, 0);
    tsLayout->setSpacing(4);
    m_timeSigNumCombo = new QComboBox(tsWidget);
    for (int n : {2, 3, 4, 5, 6, 7, 8})
        m_timeSigNumCombo->addItem(QString::number(n), n);
    m_timeSigNumCombo->setCurrentIndex(2); // 4
    tsLayout->addWidget(m_timeSigNumCombo);
    tsLayout->addWidget(new QLabel("/", tsWidget));
    m_timeSigDenCombo = new QComboBox(tsWidget);
    for (int d : {2, 4, 8, 16})
        m_timeSigDenCombo->addItem(QString::number(d), d);
    m_timeSigDenCombo->setCurrentIndex(1); // 4
    tsLayout->addWidget(m_timeSigDenCombo);
    prodGrid->addWidget(tsWidget, 1, 1);

    // Key
    prodGrid->addWidget(new QLabel("Key", scrollContent), 2, 0);
    m_keyCombo = new QComboBox(scrollContent);
    for (const char* k : {"C","C#","D","D#","E","F","F#","G","G#","A","A#","B"})
        m_keyCombo->addItem(k);
    prodGrid->addWidget(m_keyCombo, 2, 1);

    // Scale
    prodGrid->addWidget(new QLabel("Scale", scrollContent), 3, 0);
    m_scaleCombo = new QComboBox(scrollContent);
    for (const char* s : {"major","minor","dorian","mixolydian","phrygian",
                          "lydian","harmonic_minor","pentatonic","blues"})
        m_scaleCombo->addItem(s);
    prodGrid->addWidget(m_scaleCombo, 3, 1);

    // Chord Style
    prodGrid->addWidget(new QLabel("Chord Style", scrollContent), 4, 0);
    m_chordStyleCombo = new QComboBox(scrollContent);
    for (const char* cs : {"default","future_bass_chords","house_chords",
                           "trap_chords","ambient_chords","lofi_chords","jazz_chords"})
        m_chordStyleCombo->addItem(cs);
    prodGrid->addWidget(m_chordStyleCombo, 4, 1);

    // Drum Style
    prodGrid->addWidget(new QLabel("Drum Style", scrollContent), 5, 0);
    m_drumStyleCombo = new QComboBox(scrollContent);
    for (const char* ds : {"default","future_bass","house","trap","ambient","lofi","jazz"})
        m_drumStyleCombo->addItem(ds);
    prodGrid->addWidget(m_drumStyleCombo, 5, 1);

    contentLayout->addLayout(prodGrid);
    contentLayout->addSpacing(8);

    // ── Master FX section ─────────────────────────────────────────────────
    m_fxLabel = new QLabel(QStringLiteral("Master FX"), scrollContent);
    contentLayout->addWidget(m_fxLabel);

    m_fxLayout = new QVBoxLayout;
    m_fxLayout->setContentsMargins(0, 0, 0, 0);
    m_fxLayout->setSpacing(4);
    contentLayout->addLayout(m_fxLayout);

    m_addFxBtn = new QPushButton(QStringLiteral("+ Add FX"), scrollContent);
    m_addFxBtn->setCursor(Qt::PointingHandCursor);
    connect(m_addFxBtn, &QPushButton::clicked, this, [this]() {
        if (m_fxRows.size() >= 6) return;
        addFxRow("short_reverb");
        m_addFxBtn->setVisible(m_fxRows.size() < 6);
    });
    contentLayout->addWidget(m_addFxBtn);
    contentLayout->addSpacing(8);

    // ── Instruments section ───────────────────────────────────────────────
    m_instrLabel = new QLabel(QStringLiteral("Instruments"), scrollContent);
    contentLayout->addWidget(m_instrLabel);

    m_instrLayout = new QVBoxLayout;
    m_instrLayout->setContentsMargins(0, 0, 0, 0);
    m_instrLayout->setSpacing(4);
    contentLayout->addLayout(m_instrLayout);

    m_addInstrBtn = new QPushButton(QStringLiteral("+ Add Instrument"), scrollContent);
    m_addInstrBtn->setCursor(Qt::PointingHandCursor);
    connect(m_addInstrBtn, &QPushButton::clicked, this, [this]() {
        addInstrumentSlot();
    });
    contentLayout->addWidget(m_addInstrBtn);

    contentLayout->addStretch(1);

    m_scrollArea->setWidget(scrollContent);
    outerLayout->addWidget(m_scrollArea, 1);
    outerLayout->addSpacing(8);

    // ── Action buttons ────────────────────────────────────────────────────
    auto* btnRow = new QHBoxLayout;
    btnRow->setSpacing(8);

    m_resetBtn = new QPushButton(QStringLiteral("Reset"), this);
    m_saveBtn  = new QPushButton(QStringLiteral("Save"), this);
    m_applyBtn = new QPushButton(QStringLiteral("Apply"), this);

    m_resetBtn->setCursor(Qt::PointingHandCursor);
    m_saveBtn->setCursor(Qt::PointingHandCursor);
    m_applyBtn->setCursor(Qt::PointingHandCursor);

    connect(m_resetBtn, &QPushButton::clicked, this, &GenreConfigPopup::resetToDefaults);
    connect(m_saveBtn,  &QPushButton::clicked, this, &GenreConfigPopup::saveToSettings);
    connect(m_applyBtn, &QPushButton::clicked, this, &GenreConfigPopup::applyChanges);

    btnRow->addWidget(m_resetBtn);
    btnRow->addStretch(1);
    btnRow->addWidget(m_saveBtn);
    btnRow->addWidget(m_applyBtn);
    outerLayout->addLayout(btnRow);
}

// ---------------------------------------------------------------------------
// addFxRow — add a master FX combo + remove button
// ---------------------------------------------------------------------------

void GenreConfigPopup::addFxRow(const QString& fxName)
{
    auto* container = new QWidget;
    auto* hl = new QHBoxLayout(container);
    hl->setContentsMargins(0, 0, 0, 0);
    hl->setSpacing(4);

    auto* combo = new QComboBox(container);
    for (const char* fx : {"short_reverb","hall_reverb","huge_reverb","dark_reverb",
                           "chorus","tape_sat","hard_clip"})
        combo->addItem(fx);
    int idx = combo->findText(fxName);
    if (idx >= 0) combo->setCurrentIndex(idx);

    auto* removeBtn = new QToolButton(container);
    removeBtn->setText(QString::fromUtf8("\xc3\x97")); // ×
    removeBtn->setFixedSize(24, 24);
    removeBtn->setCursor(Qt::PointingHandCursor);

    hl->addWidget(combo, 1);
    hl->addWidget(removeBtn);

    m_fxLayout->addWidget(container);

    FxRow row;
    row.combo = combo;
    row.removeBtn = removeBtn;
    row.container = container;
    m_fxRows.append(row);

    connect(removeBtn, &QToolButton::clicked, this, [this, container]() {
        for (int i = 0; i < m_fxRows.size(); ++i) {
            if (m_fxRows[i].container == container) {
                m_fxLayout->removeWidget(container);
                container->deleteLater();
                m_fxRows.remove(i);
                break;
            }
        }
        m_addFxBtn->setVisible(m_fxRows.size() < 6);
    });
}

// ---------------------------------------------------------------------------
// Instruments
// ---------------------------------------------------------------------------

void GenreConfigPopup::rebuildInstrumentWidgets()
{
    // Clear existing
    for (auto& w : m_instrWidgets) {
        m_instrLayout->removeWidget(w.container);
        w.container->deleteLater();
    }
    m_instrWidgets.clear();
}

void GenreConfigPopup::addInstrumentSlot()
{
    if (m_instrWidgets.size() >= 10) return;

    auto* container = new QWidget;
    container->setObjectName("InstrSlotCard");
    auto* vl = new QVBoxLayout(container);
    vl->setContentsMargins(8, 6, 8, 6);
    vl->setSpacing(4);

    // Header row: "Slot N" + remove button
    auto* headerRow = new QHBoxLayout;
    headerRow->setContentsMargins(0, 0, 0, 0);
    auto* slotTitle = new QLabel(QStringLiteral("Slot %1").arg(m_instrWidgets.size() + 1), container);
    auto* removeBtn = new QToolButton(container);
    removeBtn->setText(QString::fromUtf8("\xc3\x97")); // ×
    removeBtn->setFixedSize(20, 20);
    removeBtn->setCursor(Qt::PointingHandCursor);
    headerRow->addWidget(slotTitle);
    headerRow->addStretch(1);
    headerRow->addWidget(removeBtn);
    vl->addLayout(headerRow);

    // Grid: Name, Plugin, Preset
    auto* grid = new QGridLayout;
    grid->setContentsMargins(0, 0, 0, 0);
    grid->setHorizontalSpacing(6);
    grid->setVerticalSpacing(3);

    grid->addWidget(new QLabel("Name", container), 0, 0);
    auto* nameEdit = new QLineEdit(QStringLiteral("New Instrument"), container);
    grid->addWidget(nameEdit, 0, 1);

    grid->addWidget(new QLabel("Plugin", container), 1, 0);
    auto* pluginCombo = new QComboBox(container);
    // Populate from backend
    if (m_backend) {
        const QVariantList plugins = m_backend->getAvailablePlugins();
        for (const QVariant& v : plugins) {
            const QVariantMap m = v.toMap();
            pluginCombo->addItem(m.value("displayName").toString(),
                                 m.value("name").toString());
        }
    }
    grid->addWidget(pluginCombo, 1, 1);

    grid->addWidget(new QLabel("Preset", container), 2, 0);
    auto* presetCombo = new QComboBox(container);
    presetCombo->addItem(QStringLiteral("(default)"));
    // Load presets for current plugin
    if (m_backend && pluginCombo->count() > 0) {
        const QString pluginName = pluginCombo->currentData().toString();
        const QStringList presets = m_backend->getPresetsForPlugin(pluginName);
        for (const QString& pr : presets)
            presetCombo->addItem(pr);
    }
    grid->addWidget(presetCombo, 2, 1);

    // Browse button — opens instrument catalog search
    auto* browseBtn = new QPushButton(QStringLiteral("Browse..."), container);
    browseBtn->setCursor(Qt::PointingHandCursor);
    browseBtn->setFixedHeight(22);
    grid->addWidget(browseBtn, 3, 0, 1, 2);

    vl->addLayout(grid);

    // Update presets when plugin changes
    connect(pluginCombo, QOverload<int>::of(&QComboBox::activated),
            this, [this, pluginCombo, presetCombo](int) {
        presetCombo->clear();
        presetCombo->addItem(QStringLiteral("(default)"));
        if (m_backend) {
            const QString pluginName = pluginCombo->currentData().toString();
            const QStringList presets = m_backend->getPresetsForPlugin(pluginName);
            for (const QString& pr : presets)
                presetCombo->addItem(pr);
        }
    });

    // Browse button handler — search catalog and fill slot
    connect(browseBtn, &QPushButton::clicked, this,
            [this, nameEdit, pluginCombo, presetCombo]() {
        // Show a simple input dialog to search the catalog
        bool ok = false;
        const QString query = QInputDialog::getText(
            this, QStringLiteral("Browse Instruments"),
            QStringLiteral("Search for an instrument:"),
            QLineEdit::Normal, {}, &ok);
        if (!ok || query.isEmpty()) return;

        // Synchronous RPC search via backend
        if (!m_backend) return;
        QVariantList results;
        bool done = false;
        auto conn = connect(m_backend, &AIBackend::instrumentSearchResults,
                           this, [&results, &done](const QVariantList& items, int, bool) {
            results = items;
            done = true;
        });
        m_backend->searchInstruments(query, {}, {}, 0, 20);
        // Spin briefly to get results
        QElapsedTimer t; t.start();
        while (!done && t.elapsed() < 3000)
            QCoreApplication::processEvents(QEventLoop::AllEvents, 50);
        disconnect(conn);

        if (results.isEmpty()) return;

        // Build string list for user to pick
        QStringList labels;
        for (const QVariant& v : results)
            labels << v.toMap().value(QStringLiteral("name")).toString();

        const QString choice = QInputDialog::getItem(
            this, QStringLiteral("Select Instrument"),
            QStringLiteral("Choose:"), labels, 0, false, &ok);
        if (!ok) return;

        // Find the chosen entry
        int choiceIdx = labels.indexOf(choice);
        if (choiceIdx < 0) return;
        const QVariantMap entry = results[choiceIdx].toMap();

        // Fill slot
        nameEdit->setText(entry.value(QStringLiteral("name")).toString());
        const QString plugin = entry.value(QStringLiteral("plugin")).toString();
        for (int i = 0; i < pluginCombo->count(); ++i) {
            if (pluginCombo->itemData(i).toString() == plugin) {
                pluginCombo->setCurrentIndex(i);
                // Refresh presets
                presetCombo->clear();
                presetCombo->addItem(QStringLiteral("(default)"));
                if (m_backend) {
                    const QStringList presets = m_backend->getPresetsForPlugin(plugin);
                    for (const QString& pr : presets)
                        presetCombo->addItem(pr);
                }
                break;
            }
        }
        // Try to select the preset
        const QString preset = entry.value(QStringLiteral("preset")).toString();
        if (!preset.isEmpty()) {
            for (int i = 0; i < presetCombo->count(); ++i) {
                if (presetCombo->itemText(i) == preset) {
                    presetCombo->setCurrentIndex(i);
                    break;
                }
            }
        }
    });

    m_instrLayout->addWidget(container);

    InstrSlotWidgets sw;
    sw.nameEdit = nameEdit;
    sw.pluginCombo = pluginCombo;
    sw.presetCombo = presetCombo;
    sw.removeBtn = removeBtn;
    sw.container = container;
    m_instrWidgets.append(sw);

    // Remove handler
    connect(removeBtn, &QToolButton::clicked, this, [this, container]() {
        for (int i = 0; i < m_instrWidgets.size(); ++i) {
            if (m_instrWidgets[i].container == container) {
                removeInstrumentSlot(i);
                break;
            }
        }
    });

    m_addInstrBtn->setVisible(m_instrWidgets.size() < 10);
}

void GenreConfigPopup::removeInstrumentSlot(int index)
{
    if (index < 0 || index >= m_instrWidgets.size()) return;
    auto& w = m_instrWidgets[index];
    m_instrLayout->removeWidget(w.container);
    w.container->deleteLater();
    m_instrWidgets.remove(index);
    m_addInstrBtn->setVisible(m_instrWidgets.size() < 10);
}

// ---------------------------------------------------------------------------
// loadGenre — populate all widgets from static table + QSettings overrides
// ---------------------------------------------------------------------------

void GenreConfigPopup::loadGenre(const QString& key)
{
    m_currentGenreKey = key;

    // Update header
    if (key == QStringLiteral("custom"))
        m_headerLabel->setText(QStringLiteral("CUSTOM GENRE SETTINGS"));
    else {
        const GenreModeCfg* cfg = findGenreMode(key);
        m_headerLabel->setText(QString("GENRE SETTINGS \xe2\x80\x94 %1")
            .arg(cfg ? QString(cfg->displayName).toUpper() : key.toUpper()));
    }

    // Read QSettings overrides for built-in genres, or custom genre settings
    QSettings settings;
    const QString overridePrefix = (key == QStringLiteral("custom"))
        ? QStringLiteral("Wavy/GenreCustom/")
        : QStringLiteral("Wavy/GenreOverrides/") + key + "/";

    // Default values from static table (or custom defaults)
    int bpm = 120;
    int tsNum = 4, tsDen = 4;
    QString musKey = "C", musScale = "major";
    QString chordStyle = "default", drumStyle = "default";
    QStringList fxList;

    if (key != QStringLiteral("custom")) {
        const GenreModeCfg* cfg = findGenreMode(key);
        if (cfg) {
            bpm = cfg->bpm;
            tsNum = cfg->timeSigNum;
            tsDen = cfg->timeSigDen;
            musKey = QString(cfg->defaultKey);
            musScale = QString(cfg->defaultScale);
            chordStyle = QString(cfg->chordStyle);
            drumStyle = QString(cfg->drumStyle);
            for (int i = 0; i < 6 && cfg->masterFx[i]; ++i)
                fxList.append(QString(cfg->masterFx[i]));
        }
    }

    // Overlay QSettings overrides
    bpm       = settings.value(overridePrefix + "bpm", bpm).toInt();
    tsNum     = settings.value(overridePrefix + "timeSigNum", tsNum).toInt();
    tsDen     = settings.value(overridePrefix + "timeSigDen", tsDen).toInt();
    musKey    = settings.value(overridePrefix + "key", musKey).toString();
    musScale  = settings.value(overridePrefix + "scale", musScale).toString();
    chordStyle = settings.value(overridePrefix + "chordStyle", chordStyle).toString();
    drumStyle  = settings.value(overridePrefix + "drumStyle", drumStyle).toString();

    // Check for FX overrides
    const QByteArray fxJson = settings.value(overridePrefix + "masterFx").toByteArray();
    if (!fxJson.isEmpty()) {
        QJsonDocument doc = QJsonDocument::fromJson(fxJson);
        if (doc.isArray()) {
            fxList.clear();
            for (const auto& v : doc.array())
                fxList.append(v.toString());
        }
    }

    // Populate production widgets
    m_bpmSpin->setValue(bpm);

    int tsNumIdx = m_timeSigNumCombo->findData(tsNum);
    if (tsNumIdx >= 0) m_timeSigNumCombo->setCurrentIndex(tsNumIdx);
    int tsDenIdx = m_timeSigDenCombo->findData(tsDen);
    if (tsDenIdx >= 0) m_timeSigDenCombo->setCurrentIndex(tsDenIdx);

    int keyIdx = m_keyCombo->findText(musKey);
    if (keyIdx >= 0) m_keyCombo->setCurrentIndex(keyIdx);

    int scaleIdx = m_scaleCombo->findText(musScale);
    if (scaleIdx >= 0) m_scaleCombo->setCurrentIndex(scaleIdx);

    int csIdx = m_chordStyleCombo->findText(chordStyle);
    if (csIdx >= 0) m_chordStyleCombo->setCurrentIndex(csIdx);

    int dsIdx = m_drumStyleCombo->findText(drumStyle);
    if (dsIdx >= 0) m_drumStyleCombo->setCurrentIndex(dsIdx);

    // Rebuild FX rows
    for (auto& row : m_fxRows) {
        m_fxLayout->removeWidget(row.container);
        row.container->deleteLater();
    }
    m_fxRows.clear();
    for (const QString& fx : fxList)
        addFxRow(fx);
    m_addFxBtn->setVisible(m_fxRows.size() < 6);

    // Rebuild instrument slots
    rebuildInstrumentWidgets();
    const QVariantList instrConfig = m_backend->getGenreInstrumentConfig(key);
    for (const QVariant& v : instrConfig) {
        const QVariantMap slot = v.toMap();
        addInstrumentSlot();
        auto& sw = m_instrWidgets.last();
        sw.nameEdit->setText(slot.value("name").toString());
        // Set plugin
        const QString pluginName = slot.value("plugin").toString();
        for (int i = 0; i < sw.pluginCombo->count(); ++i) {
            if (sw.pluginCombo->itemData(i).toString() == pluginName) {
                sw.pluginCombo->setCurrentIndex(i);
                break;
            }
        }
        // Refresh and set preset
        sw.presetCombo->clear();
        sw.presetCombo->addItem(QStringLiteral("(default)"));
        if (m_backend) {
            const QStringList presets = m_backend->getPresetsForPlugin(pluginName);
            for (const QString& pr : presets)
                sw.presetCombo->addItem(pr);
        }
        const QString preset = slot.value("preset").toString();
        if (!preset.isEmpty()) {
            int pi = sw.presetCombo->findText(preset);
            if (pi >= 0) sw.presetCombo->setCurrentIndex(pi);
        }
    }

    // For custom genre with no saved instruments, add one default slot
    if (key == QStringLiteral("custom") && m_instrWidgets.isEmpty())
        addInstrumentSlot();

    m_addInstrBtn->setVisible(m_instrWidgets.size() < 10);
    applyThemeColors();
}

// ---------------------------------------------------------------------------
// saveToSettings — persist current popup state to QSettings
// ---------------------------------------------------------------------------

void GenreConfigPopup::saveToSettings()
{
    QSettings settings;
    const QString prefix = (m_currentGenreKey == QStringLiteral("custom"))
        ? QStringLiteral("Wavy/GenreCustom/")
        : QStringLiteral("Wavy/GenreOverrides/") + m_currentGenreKey + "/";

    settings.setValue(prefix + "bpm", m_bpmSpin->value());
    settings.setValue(prefix + "timeSigNum", m_timeSigNumCombo->currentData().toInt());
    settings.setValue(prefix + "timeSigDen", m_timeSigDenCombo->currentData().toInt());
    settings.setValue(prefix + "key", m_keyCombo->currentText());
    settings.setValue(prefix + "scale", m_scaleCombo->currentText());
    settings.setValue(prefix + "chordStyle", m_chordStyleCombo->currentText());
    settings.setValue(prefix + "drumStyle", m_drumStyleCombo->currentText());

    // Master FX as JSON array
    QJsonArray fxArr;
    for (const auto& row : m_fxRows)
        fxArr.append(row.combo->currentText());
    settings.setValue(prefix + "masterFx",
                     QJsonDocument(fxArr).toJson(QJsonDocument::Compact));

    // Instruments — use existing backend method for consistency with ToolsPage
    QVariantList instrSlots;
    for (const auto& sw : m_instrWidgets) {
        QVariantMap slot;
        slot[QStringLiteral("name")]   = sw.nameEdit->text();
        slot[QStringLiteral("plugin")] = sw.pluginCombo->currentData().toString();
        const QString preset = sw.presetCombo->currentText();
        slot[QStringLiteral("preset")] = (preset == "(default)") ? QString() : preset;
        slot[QStringLiteral("color")]  = QStringLiteral("#3498DB"); // default color
        instrSlots.append(slot);
    }
    m_backend->saveGenreInstrumentOverride(m_currentGenreKey, instrSlots);

    qDebug() << "[GenreConfigPopup] saved settings for" << m_currentGenreKey;
}

// ---------------------------------------------------------------------------
// resetToDefaults — clear QSettings overrides, reload from static table
// ---------------------------------------------------------------------------

void GenreConfigPopup::resetToDefaults()
{
    QSettings settings;
    if (m_currentGenreKey == QStringLiteral("custom")) {
        settings.remove(QStringLiteral("Wavy/GenreCustom"));
    } else {
        settings.remove(QStringLiteral("Wavy/GenreOverrides/") + m_currentGenreKey);
    }
    m_backend->resetGenreInstrumentDefaults(m_currentGenreKey);

    // Reload UI from defaults
    loadGenre(m_currentGenreKey);
    qDebug() << "[GenreConfigPopup] reset to defaults for" << m_currentGenreKey;
}

// ---------------------------------------------------------------------------
// applyChanges — save + emit signal to apply to DAW
// ---------------------------------------------------------------------------

void GenreConfigPopup::applyChanges()
{
    saveToSettings();
    emit applyRequested(m_currentGenreKey);
    close();
}

// ---------------------------------------------------------------------------
// applyThemeColors
// ---------------------------------------------------------------------------

void GenreConfigPopup::applyThemeColors()
{
    auto* th = Wavy::ThemeManager::themeObject();
    if (!th) return;

    const QColor accent  = th->accent();
    const QColor bg      = th->bg();
    const QColor surface = th->surface();
    const QColor fg      = th->fg();
    const QColor dim     = th->dim();
    const QColor outline = th->outline();

    // LCD background (dark, accent-tinted) — same formula as TransportBar
    const QColor lcdBg = QColor(
        qMin(255, accent.red()   / 12 + 4),
        qMin(255, accent.green() / 12 + 4),
        qMin(255, accent.blue()  / 12 + 7));
    const QColor lcdBorder = QColor(
        qMin(255, int(accent.red()   * 0.35)),
        qMin(255, int(accent.green() * 0.35)),
        qMin(255, int(accent.blue()  * 0.35)));

    // Section headers
    const QString sectionStyle = QString(
        "color: %1; font-size: 11px; font-weight: bold; "
        "letter-spacing: 1px; background: transparent; padding: 2px 0;")
        .arg(accent.name());

    m_headerLabel->setStyleSheet(QString(
        "color: %1; font-size: 13px; font-weight: bold; "
        "letter-spacing: 2px; background: transparent;").arg(accent.name()));
    m_prodLabel->setStyleSheet(sectionStyle);
    m_fxLabel->setStyleSheet(sectionStyle);
    m_instrLabel->setStyleSheet(sectionStyle);

    // Labels in grid
    const QString labelStyle = QString(
        "color: %1; font-size: 10px; background: transparent;").arg(dim.name());

    // Input widget shared style
    const QString inputStyle = QString(R"(
        QSpinBox, QComboBox, QLineEdit {
            background: %1; color: %2; border: 1px solid %3;
            border-radius: 3px; padding: 2px 6px;
            font-size: 11px; font-family: 'Courier New', monospace;
        }
        QSpinBox:focus, QComboBox:focus, QLineEdit:focus {
            border: 1px solid %2;
        }
        QComboBox::drop-down {
            border: none; width: 16px;
        }
        QComboBox::down-arrow {
            image: none;
            border-left: 3px solid transparent;
            border-right: 3px solid transparent;
            border-top: 4px solid %2;
            margin-right: 4px;
        }
        QComboBox QAbstractItemView {
            background: %1; color: %2; border: 1px solid %3;
            selection-background-color: %3; selection-color: %2;
            outline: none;
        }
    )").arg(lcdBg.name(), accent.name(), lcdBorder.name());

    // Apply to scroll area content
    if (m_scrollArea && m_scrollArea->widget()) {
        m_scrollArea->widget()->setStyleSheet(inputStyle + labelStyle);
        m_scrollArea->setStyleSheet(QStringLiteral(
            "QScrollArea { background: transparent; }"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical { background: %1; border-radius: 3px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }")
            .arg(lcdBorder.name()));
    }

    // Instrument slot cards
    const QString cardStyle = QString(
        "QWidget#InstrSlotCard { background: %1; border: 1px solid %2; "
        "border-radius: 4px; }").arg(lcdBg.name(), lcdBorder.name());
    for (auto& sw : m_instrWidgets) {
        if (sw.container)
            sw.container->setStyleSheet(cardStyle);
    }

    // Buttons
    m_applyBtn->setStyleSheet(QString(
        "QPushButton { background: %1; color: %2; border: none; border-radius: 4px; "
        "padding: 6px 16px; font-weight: bold; font-size: 11px; }"
        "QPushButton:hover { background: %3; }")
        .arg(accent.name(), bg.name(),
             accent.lighter(120).name()));

    m_saveBtn->setStyleSheet(QString(
        "QPushButton { background: %1; color: %2; border: 1px solid %3; border-radius: 4px; "
        "padding: 6px 16px; font-size: 11px; }"
        "QPushButton:hover { background: %4; }")
        .arg(lcdBg.name(), fg.name(), lcdBorder.name(), surface.name()));

    m_resetBtn->setStyleSheet(QString(
        "QPushButton { background: transparent; color: %1; border: 1px solid %1; "
        "border-radius: 4px; padding: 6px 16px; font-size: 11px; }"
        "QPushButton:hover { background: %2; }")
        .arg(dim.name(), lcdBg.name()));

    m_addFxBtn->setStyleSheet(QString(
        "QPushButton { background: transparent; color: %1; border: 1px dashed %2; "
        "border-radius: 3px; padding: 4px; font-size: 10px; }"
        "QPushButton:hover { background: %3; }")
        .arg(accent.name(), lcdBorder.name(), lcdBg.name()));

    m_addInstrBtn->setStyleSheet(m_addFxBtn->styleSheet());

    update();
}
