#include "ModelManagerPanel.h"
#include "ModelManager.h"

#include <QHBoxLayout>
#include <QGroupBox>
#include <QScrollArea>
#include <QStorageInfo>
#include <QStandardPaths>
#include <QFrame>
#include <QFont>
#include <QSizePolicy>
#include <QStyle>
#include <QMessageBox>

static constexpr qint64 GB = 1024LL * 1024 * 1024;

// ---------------------------------------------------------------------------
// Construction
// ---------------------------------------------------------------------------

ModelManagerPanel::ModelManagerPanel(ModelManager* mgr, QWidget* parent)
    : QWidget(parent), m_mgr(mgr)
{
    buildUI();

    connect(mgr, &ModelManager::modelStatusChanged,   this, &ModelManagerPanel::onStatusChanged);
    connect(mgr, &ModelManager::downloadProgress,     this, &ModelManagerPanel::onDownloadProgress);
    connect(mgr, &ModelManager::downloadFinished,     this, &ModelManagerPanel::onDownloadFinished);
    connect(mgr, &ModelManager::allModelsReady,       this, &ModelManagerPanel::allModelsReady);

    refresh();
}

// ---------------------------------------------------------------------------
// UI construction
// ---------------------------------------------------------------------------

void ModelManagerPanel::buildUI()
{
    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(16, 16, 16, 16);
    root->setSpacing(12);

    // ── Header ───────────────────────────────────────────────────────────────
    auto* headerRow = new QHBoxLayout;
    auto* title = new QLabel("AI Model Status", this);
    QFont f = title->font();
    f.setPointSize(13); f.setBold(true);
    title->setFont(f);
    title->setObjectName("sectionTitle");
    headerRow->addWidget(title);
    headerRow->addStretch();

    m_diskLabel = new QLabel(this);
    m_diskLabel->setObjectName("aiDailyCounter");
    headerRow->addWidget(m_diskLabel);
    root->addLayout(headerRow);

    // ── Separator ────────────────────────────────────────────────────────────
    auto* line = new QFrame(this);
    line->setFrameShape(QFrame::HLine);
    line->setObjectName("separator");
    root->addWidget(line);

    // ── Scrollable content ───────────────────────────────────────────────────
    auto* scroll = new QScrollArea(this);
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);

    auto* content = new QWidget;
    auto* contentLayout = new QVBoxLayout(content);
    contentLayout->setContentsMargins(0, 0, 0, 0);
    contentLayout->setSpacing(16);

    // Cloud API section
    buildCloudApiSection(contentLayout);

    // Local models section
    buildLocalModelsSection(contentLayout);

    contentLayout->addStretch();
    scroll->setWidget(content);
    root->addWidget(scroll, 1);

    // ── Download all recommended button ──────────────────────────────────────
    m_downloadAllRecommendedBtn = new QPushButton(
        "\u2193  Download All Recommended (~15 GB)", this);
    m_downloadAllRecommendedBtn->setObjectName("aiGenerateBtn");
    m_downloadAllRecommendedBtn->setMinimumHeight(36);
    connect(m_downloadAllRecommendedBtn, &QPushButton::clicked, this, [this]() {
        m_mgr->downloadRecommendedModels();
        m_downloadAllRecommendedBtn->setEnabled(false);
        m_downloadAllRecommendedBtn->setText("\u23f3  Downloading …");
    });
    root->addWidget(m_downloadAllRecommendedBtn);
}

void ModelManagerPanel::buildCloudApiSection(QVBoxLayout* parent)
{
    auto* group = new QGroupBox("Cloud API Models", this);
    group->setObjectName("modelGroup");
    auto* layout = new QVBoxLayout(group);
    layout->setSpacing(6);

    auto* desc = new QLabel(
        "These models run in the cloud — no download required. "
        "Status shows whether an API key is configured.", group);
    desc->setWordWrap(true);
    desc->setObjectName("aboutDesc");
    layout->addWidget(desc);

    // Will be populated in refresh()
    m_cloudApiSection = group;
    parent->addWidget(group);
}

void ModelManagerPanel::buildLocalModelsSection(QVBoxLayout* parent)
{
    auto* group = new QGroupBox("Local Models", this);
    group->setObjectName("modelGroup");
    auto* layout = new QVBoxLayout(group);
    layout->setSpacing(4);

    auto* desc = new QLabel(
        "Download for offline use or for higher quality than the cloud default. "
        "Recommended models are starred.", group);
    desc->setWordWrap(true);
    desc->setObjectName("aboutDesc");
    layout->addWidget(desc);

    // Row container
    auto* rowContainer = new QWidget(group);
    m_localRowLayout = new QVBoxLayout(rowContainer);
    m_localRowLayout->setContentsMargins(0, 4, 0, 0);
    m_localRowLayout->setSpacing(4);
    layout->addWidget(rowContainer);

    parent->addWidget(group);
}

ModelManagerPanel::ModelRow ModelManagerPanel::buildLocalModelRow(
    const QString& name, const QString& displayName,
    bool recommended, double diskSizeGb)
{
    auto* row = new QWidget(this);
    row->setObjectName("modelRow");
    row->setMinimumHeight(68);
    row->setMaximumHeight(80);

    auto* hl = new QHBoxLayout(row);
    hl->setContentsMargins(10, 8, 10, 8);
    hl->setSpacing(10);

    // Left col: name + recommended badge
    auto* infoCol = new QVBoxLayout;
    infoCol->setSpacing(2);

    auto* nameLabel = new QLabel(displayName, row);
    nameLabel->setObjectName("modelName");
    QFont nf = nameLabel->font();
    nf.setBold(true);
    nameLabel->setFont(nf);
    infoCol->addWidget(nameLabel);

    if (recommended) {
        auto* badge = new QLabel("\u2605 Recommended for best quality", row);
        badge->setObjectName("aiDailyCounter");
        QFont bf = badge->font();
        bf.setItalic(true);
        badge->setFont(bf);
        badge->setStyleSheet("color: #f0c040;");
        infoCol->addWidget(badge);
    }

    hl->addLayout(infoCol, 3);

    // Mid col: disk size
    auto* sizeLabel = new QLabel(
        diskSizeGb > 0 ? QString("%1 GB").arg(diskSizeGb, 0, 'f', 1) : "–", row);
    sizeLabel->setObjectName("aiDailyCounter");
    sizeLabel->setFixedWidth(55);
    sizeLabel->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    hl->addWidget(sizeLabel);

    // Progress bar (hidden when not downloading)
    auto* prog = new QProgressBar(row);
    prog->setRange(0, 100);
    prog->setVisible(false);
    prog->setFixedWidth(110);
    prog->setMaximumHeight(6);
    prog->setObjectName("aiProgressBar");
    hl->addWidget(prog);

    // Status label
    auto* statusLabel = new QLabel(row);
    statusLabel->setFixedWidth(90);
    statusLabel->setAlignment(Qt::AlignCenter);
    hl->addWidget(statusLabel);

    // Action button (Download / Update)
    auto* actionBtn = new QPushButton("\u2193 Download", row);
    actionBtn->setObjectName("aiGenerateBtn");
    actionBtn->setFixedSize(100, 28);
    connect(actionBtn, &QPushButton::clicked, this, [this, name]() {
        onDownloadClicked(name);
    });
    hl->addWidget(actionBtn);

    // Uninstall button (only visible when installed)
    auto* uninstallBtn = new QPushButton("\U0001f5d1", row);
    uninstallBtn->setToolTip("Uninstall model");
    uninstallBtn->setFixedSize(28, 28);
    uninstallBtn->setVisible(false);
    connect(uninstallBtn, &QPushButton::clicked, this, [this, name]() {
        onUninstallClicked(name);
    });
    hl->addWidget(uninstallBtn);

    ModelRow mr;
    mr.widget       = row;
    mr.statusLabel  = statusLabel;
    mr.progress     = prog;
    mr.actionBtn    = actionBtn;
    mr.uninstallBtn = uninstallBtn;

    m_localRowLayout->addWidget(row);
    return mr;
}

// ---------------------------------------------------------------------------
// Refresh
// ---------------------------------------------------------------------------

void ModelManagerPanel::refresh()
{
    // ── Clear existing rows ────────────────────────────────────────────────
    for (auto& r : m_rows)
        if (r.widget) r.widget->deleteLater();
    m_rows.clear();

    // Clear cloud API rows
    for (auto* lbl : m_cloudRows)
        lbl->deleteLater();
    m_cloudRows.clear();

    // Remove all items from the cloud section layout except the desc label
    if (auto* grpLayout = qobject_cast<QGroupBox*>(m_cloudApiSection)
                              ? static_cast<QVBoxLayout*>(m_cloudApiSection->layout())
                              : nullptr) {
        // Remove items after index 0 (the desc label)
        while (grpLayout->count() > 1) {
            auto* item = grpLayout->takeAt(1);
            if (item->widget()) item->widget()->deleteLater();
            delete item;
        }
    }

    // Remove all local rows
    while (m_localRowLayout->count() > 0) {
        auto* item = m_localRowLayout->takeAt(0);
        if (item->widget()) item->widget()->deleteLater();
        delete item;
    }

    // ── Rebuild from model catalog ─────────────────────────────────────────
    const auto& models = m_mgr->models();

    // Cloud API section
    if (auto* grpLayout = m_cloudApiSection
                              ? static_cast<QVBoxLayout*>(m_cloudApiSection->layout())
                              : nullptr) {
        for (const auto& info : models) {
            if (!info.isCloudApi) continue;

            auto* rowWidget = new QWidget(m_cloudApiSection);
            auto* rl = new QHBoxLayout(rowWidget);
            rl->setContentsMargins(6, 4, 6, 4);

            // Icon
            auto* icon = new QLabel(info.apiKeyConfigured ? "\u2713" : "\u25cb", rowWidget);
            icon->setFixedWidth(20);
            icon->setObjectName(info.apiKeyConfigured ? "aiStatusOk" : "aiDailyCounter");
            rl->addWidget(icon);

            // Name
            auto* nameLabel = new QLabel(info.displayName, rowWidget);
            QFont nf = nameLabel->font();
            nf.setBold(true);
            nameLabel->setFont(nf);
            rl->addWidget(nameLabel);

            rl->addStretch();

            // Status
            QString statusText;
            if (info.apiKeyConfigured && !info.apiKeyEnvVar.isEmpty()) {
                statusText = info.apiKeyEnvVar == "HF_TOKEN"
                    ? "Free \u00b7 No key needed"
                    : QString("%1 set").arg(info.apiKeyEnvVar);
            } else if (!info.apiKeyEnvVar.isEmpty()) {
                statusText = QString("%1 needed").arg(info.apiKeyEnvVar);
            }
            auto* statusLabel = new QLabel(statusText, rowWidget);
            statusLabel->setObjectName(info.apiKeyConfigured ? "aiStatusOk" : "aiStatusOffline");
            statusLabel->setToolTip(
                info.apiKeyEnvVar.isEmpty()
                    ? "No API key required"
                    : QString("Set env var: %1").arg(info.apiKeyEnvVar));
            rl->addWidget(statusLabel);

            grpLayout->addWidget(rowWidget);
            m_cloudRows.insert(info.name, statusLabel);
        }
    }

    // Local models section
    for (const auto& info : models) {
        if (info.isCloudApi) continue;
        auto row = buildLocalModelRow(info.name, info.displayName,
                                     info.recommended, info.diskSizeGb);
        m_rows.insert(info.name, row);
        setRowStatus(info.name, info.downloaded, info.loaded);
    }

    // Disk space
    const qint64 free = availableDiskBytes();
    m_diskLabel->setText(QString("Free disk: %1 GB").arg(free / GB));
    if (free < 20 * GB)
        m_diskLabel->setObjectName("aiStatusOffline");
}

// ---------------------------------------------------------------------------
// Row status helper
// ---------------------------------------------------------------------------

void ModelManagerPanel::setRowStatus(const QString& name, bool downloaded, bool loading)
{
    auto it = m_rows.find(name);
    if (it == m_rows.end()) return;
    auto& r = it.value();

    if (loading) {
        r.statusLabel->setText("\u23f3 Loading");
        r.statusLabel->setObjectName("aiDailyCounter");
        r.actionBtn->setEnabled(false);
        r.uninstallBtn->setVisible(false);
    } else if (downloaded) {
        r.statusLabel->setText("\u2713 Installed");
        r.statusLabel->setObjectName("aiStatusOk");
        r.actionBtn->setVisible(false);
        r.progress->setVisible(false);
        r.uninstallBtn->setVisible(true);
    } else {
        r.statusLabel->setText("\u2717 Missing");
        r.statusLabel->setObjectName("aiStatusOffline");
        r.actionBtn->setVisible(true);
        r.actionBtn->setEnabled(true);
        r.actionBtn->setText("\u2193 Download");
        r.uninstallBtn->setVisible(false);
    }

    // Force style refresh
    r.statusLabel->style()->unpolish(r.statusLabel);
    r.statusLabel->style()->polish(r.statusLabel);
}

// ---------------------------------------------------------------------------
// Slots
// ---------------------------------------------------------------------------

void ModelManagerPanel::onDownloadClicked(const QString& name)
{
    auto it = m_rows.find(name);
    if (it != m_rows.end()) {
        it->progress->setVisible(true);
        it->progress->setValue(0);
        it->actionBtn->setEnabled(false);
        it->actionBtn->setText("\u23f3 …");
        it->statusLabel->setText("Downloading");
        it->statusLabel->setObjectName("aiDailyCounter");
    }
    m_mgr->downloadModel(name);
}

void ModelManagerPanel::onUninstallClicked(const QString& name)
{
    const auto& models = m_mgr->models();
    QString displayName = name;
    for (const auto& m : models)
        if (m.name == name) { displayName = m.displayName; break; }

    const auto answer = QMessageBox::question(
        this, "Uninstall Model",
        QString("Uninstall <b>%1</b>? The model files will be deleted from disk.")
            .arg(displayName),
        QMessageBox::Yes | QMessageBox::No, QMessageBox::No);

    if (answer != QMessageBox::Yes) return;

    auto it = m_rows.find(name);
    if (it != m_rows.end()) {
        it->uninstallBtn->setEnabled(false);
        it->statusLabel->setText("\u23f3 Removing");
    }
    m_mgr->uninstallModel(name);
}

void ModelManagerPanel::onDownloadProgress(const QString& name, int percent)
{
    auto it = m_rows.find(name);
    if (it == m_rows.end()) return;
    it->progress->setVisible(true);
    it->progress->setValue(percent);
}

void ModelManagerPanel::onDownloadFinished(const QString& name, bool success)
{
    auto it = m_rows.find(name);
    if (it == m_rows.end()) return;
    it->progress->setVisible(false);
    setRowStatus(name, success, false);
}

void ModelManagerPanel::onStatusChanged()
{
    // Refresh cloud connection status label in header
    if (m_mgr->allRequiredModelsReady()) {
        const QString provider = m_mgr->cloudProvider();
        // Update cloud rows for any keys that may have changed
        const auto& models = m_mgr->models();
        for (const auto& info : models) {
            auto it = m_cloudRows.find(info.name);
            if (it == m_cloudRows.end()) continue;
            QLabel* lbl = it.value();
            if (info.apiKeyConfigured) {
                lbl->setObjectName("aiStatusOk");
            } else {
                lbl->setObjectName("aiStatusOffline");
            }
            lbl->style()->unpolish(lbl);
            lbl->style()->polish(lbl);
        }
        emit allModelsReady();
    }

    // Update local model rows
    const auto& models = m_mgr->models();
    for (const auto& info : models) {
        if (!info.isCloudApi)
            setRowStatus(info.name, info.downloaded, info.loaded);
    }
}

qint64 ModelManagerPanel::availableDiskBytes() const
{
    QStorageInfo si(QStandardPaths::writableLocation(
        QStandardPaths::AppDataLocation));
    return si.bytesAvailable();
}
