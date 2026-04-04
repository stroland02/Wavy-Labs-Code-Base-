#include "StemSplitterPanel.h"
#include "../IPC/AIClient.h"
#include "../LicenseGate/LicenseManager.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGroupBox>
#include <QFileDialog>
#include <QMessageBox>
#include <QListWidgetItem>

StemSplitterPanel::StemSplitterPanel(AIClient* client, QWidget* parent)
    : QWidget(parent), m_client(client)
{
    buildUI();
}

void StemSplitterPanel::buildUI()
{
    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(16, 16, 16, 16);
    root->setSpacing(12);

    // Input
    auto* inputGroup = new QGroupBox("Input Audio", this);
    auto* igl = new QHBoxLayout(inputGroup);
    m_inputLabel = new QLabel("No file selected.", inputGroup);
    m_inputLabel->setWordWrap(true);
    auto* browseBtn = new QPushButton("Browse …", inputGroup);
    connect(browseBtn, &QPushButton::clicked, this, &StemSplitterPanel::onBrowseClicked);
    igl->addWidget(m_inputLabel, 1);
    igl->addWidget(browseBtn);
    root->addWidget(inputGroup);

    // Stem count
    auto* cfgGroup = new QGroupBox("Stem Count", this);
    auto* cgl = new QHBoxLayout(cfgGroup);
    m_stemCountCombo = new QComboBox(cfgGroup);
    m_stemCountCombo->addItem("2 stems — Vocals / Instrumental", 2);
    m_stemCountCombo->addItem("4 stems — Vocals, Drums, Bass, Other (Free+)", 4);
    m_stemCountCombo->addItem("6 stems — Vocals, Drums, Bass, Piano, Guitar, Other (Pro)", 6);
    cgl->addWidget(m_stemCountCombo);
    root->addWidget(cfgGroup);

    // Split button
    m_splitBtn = new QPushButton("⚡  Split Stems", this);
    m_splitBtn->setObjectName("aiGenerateBtn");
    m_splitBtn->setMinimumHeight(40);
    connect(m_splitBtn, &QPushButton::clicked, this, &StemSplitterPanel::onSplitClicked);
    root->addWidget(m_splitBtn);

    // Progress
    m_progress = new QProgressBar(this);
    m_progress->setRange(0, 0);
    m_progress->setVisible(false);
    m_progress->setMaximumHeight(4);
    root->addWidget(m_progress);

    // Output list
    auto* outGroup = new QGroupBox("Output Stems", this);
    auto* ogl = new QVBoxLayout(outGroup);
    m_outputList = new QListWidget(outGroup);
    ogl->addWidget(m_outputList);
    root->addWidget(outGroup, 1);
}

void StemSplitterPanel::setInputFile(const QString& path)
{
    m_inputPath = path;
    m_inputLabel->setText(path.section('/', -1));
}

void StemSplitterPanel::onBrowseClicked()
{
    const QString path = QFileDialog::getOpenFileName(
        this, "Select Audio File", {},
        "Audio Files (*.wav *.mp3 *.flac *.ogg *.aiff)");
    if (!path.isEmpty())
        setInputFile(path);
}

void StemSplitterPanel::onSplitClicked()
{
    if (m_inputPath.isEmpty()) {
        QMessageBox::warning(this, "Stem Splitter", "Please select an audio file first.");
        return;
    }
    setSplitting(true);
    m_outputList->clear();

    QVariantMap params;
    params["audio_path"] = m_inputPath;
    params["stems"]      = m_stemCountCombo->currentData().toInt();
    params["tier"]       = LicenseManager::instance()->isPro() ? "pro" : "free";

    m_client->splitStems(params,
        [this](bool ok, const QVariantMap& result) {
            QMetaObject::invokeMethod(this, [this, ok, result]() {
                onSplitFinished(ok, result);
            }, Qt::QueuedConnection);
        });
}

void StemSplitterPanel::onSplitFinished(bool ok, const QVariantMap& result)
{
    setSplitting(false);
    if (!ok) {
        QMessageBox::warning(this, "Stem Splitter",
                             result.value("error").toString());
        return;
    }

    const QVariantMap stems = result.value("stems").toMap();
    QStringList paths, names;
    for (auto it = stems.begin(); it != stems.end(); ++it) {
        names << it.key();
        paths << it.value().toString();
        auto* item = new QListWidgetItem(
            QString("✓  %1 → %2").arg(it.key(), it.value().toString()),
            m_outputList);
        Q_UNUSED(item)
    }

    emit stemsReady(paths, names);
}

void StemSplitterPanel::setSplitting(bool busy)
{
    m_progress->setVisible(busy);
    m_splitBtn->setEnabled(!busy);
    m_splitBtn->setText(busy ? "⏳  Splitting …" : "⚡  Split Stems");
}
