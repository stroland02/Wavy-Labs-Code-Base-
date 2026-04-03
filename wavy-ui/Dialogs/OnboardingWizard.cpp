#include "OnboardingWizard.h"
#include "../ModelManager/ModelManager.h"
#include "../LicenseGate/LicenseManager.h"
#include "../LicenseGate/ApiKeySettings.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGroupBox>
#include <QLabel>
#include <QPushButton>
#include <QStyle>
#include <QWizardPage>
#include <QFont>
#include <QSettings>
#include <QSvgWidget>
#include <QCheckBox>
#include <QThread>
#include <QTextBrowser>
#include <QFormLayout>
#include <QTimer>
#include "../IPC/AIClient.h"

// ---------------------------------------------------------------------------
// Static helpers
// ---------------------------------------------------------------------------

bool OnboardingWizard::shouldShow()
{
    QSettings s("WavyLabs", "App");
    return !s.value("onboarding_v2_completed", false).toBool();
}

void OnboardingWizard::markCompleted()
{
    QSettings s("WavyLabs", "App");
    s.setValue("onboarding_v2_completed", true);
}

// ---------------------------------------------------------------------------
// Construction
// ---------------------------------------------------------------------------

OnboardingWizard::OnboardingWizard(ModelManager* mgr, QWidget* parent)
    : QWizard(parent), m_mgr(mgr)
{
    setWindowTitle("Welcome to Wavy Labs");
    setObjectName("onboardingWizard");
    resize(700, 520);
    setWizardStyle(QWizard::ModernStyle);
    setOption(QWizard::NoBackButtonOnStartPage);
    setOption(QWizard::NoCancelButtonOnLastPage);
    setButtonText(QWizard::FinishButton, "Start Making Music");

    buildWelcomePage();
    buildCloudPage();
    buildApiKeysPage();
    buildFinishPage();

    connect(this, &QWizard::accepted, []() { markCompleted(); });
}

// ---------------------------------------------------------------------------
// Pages
// ---------------------------------------------------------------------------

void OnboardingWizard::buildWelcomePage()
{
    auto* page = new QWizardPage;
    page->setTitle("Welcome to Wavy Labs");
    page->setSubTitle("The DAW that listens to you.");

    auto* layout = new QVBoxLayout(page);
    layout->setSpacing(16);

    auto* logoRow = new QHBoxLayout;
    auto* logo = new QSvgWidget(":/icons/wavy-labs.svg");
    logo->setFixedSize(80, 80);
    logoRow->addWidget(logo);
    logoRow->addStretch();
    layout->addLayout(logoRow);

    auto* intro = new QLabel(
        "<p><b>Wavy Labs</b> is a free, open-source AI-powered Digital Audio Workstation.</p>"
        "<p>Generate full songs from a text prompt, split any audio into stems, "
        "synthesise vocals, and mix with AI — running locally on your machine for "
        "best quality and privacy, with optional cloud APIs for quick access.</p>"
        "<p>This wizard will help you:</p>"
        "<ul>"
        "  <li>Download the AI models for local generation</li>"
        "  <li>Configure your API keys for cloud features</li>"
        "  <li>Get started with your first generation</li>"
        "</ul>",
        page);
    intro->setWordWrap(true);
    intro->setObjectName("aboutDesc");
    intro->setTextFormat(Qt::RichText);
    layout->addWidget(intro);
    layout->addStretch();

    addPage(page);
}

void OnboardingWizard::buildCloudPage()
{
    auto* page = new QWizardPage;
    page->setTitle("AI Models Setup");
    page->setSubTitle(
        "Wavy Labs uses local AI models for offline generation and cloud APIs for quick access.");

    auto* layout = new QVBoxLayout(page);
    layout->setSpacing(12);

    auto* body = new QLabel(
        "<p>Some models are <b>required</b> and will download automatically. "
        "Optional models can be selected below.</p>"
        "<p><b>Cloud APIs</b> (no download needed) — configure your API keys on the next page, "
        "or later from <b>Edit \u2192 Settings</b>.</p>",
        page);
    body->setWordWrap(true);
    body->setTextFormat(Qt::RichText);
    body->setObjectName("aboutDesc");
    layout->addWidget(body);

    m_cloudStatusLabel = new QLabel("Checking AI backend \u2026", page);
    m_cloudStatusLabel->setWordWrap(true);
    m_cloudStatusLabel->setObjectName("aiDailyCounter");
    layout->addWidget(m_cloudStatusLabel);

    connect(m_mgr, &ModelManager::allModelsReady, page, [this]() {
        m_cloudStatusLabel->setText(
            QString("\u2713 AI backend ready (%1)").arg(m_mgr->cloudProvider()));
        m_cloudStatusLabel->setObjectName("aiStatusOk");
        m_cloudStatusLabel->style()->unpolish(m_cloudStatusLabel);
        m_cloudStatusLabel->style()->polish(m_cloudStatusLabel);
    });

    // ── Required Models (auto-download) ─────────────────────────────────────
    auto* reqGroup = new QGroupBox("Required Models (auto-download with install)", page);
    auto* reqLayout = new QVBoxLayout(reqGroup);

    struct ModelEntry { const char* name; const char* label; const char* note; double gb; bool required; };
    static const ModelEntry MODELS[] = {
        { "demucs",     "Demucs v4",  "Stem splitting (downloads on first use)",   0.4, true  },
        { "prompt_cmd", "Mistral 7B", "Offline prompt commands (optional)",        4.0, false },
    };

    QList<QPair<QString, QCheckBox*>> optionalChecks;

    for (const auto& m : MODELS) {
        if (!m.required) continue;

        auto* row = new QHBoxLayout;
        auto* cb = new QCheckBox(
            QString("%1  (%2 GB) \u2014 %3").arg(m.label).arg(m.gb, 0, 'f', 1).arg(m.note),
            reqGroup);
        cb->setChecked(true);
        cb->setEnabled(false);
        cb->setObjectName("aboutDesc");
        row->addWidget(cb);
        row->addStretch();

        auto* progressLabel = new QLabel(reqGroup);
        progressLabel->setObjectName("aiDailyCounter");
        progressLabel->setFixedWidth(80);
        row->addWidget(progressLabel);

        const QString modelName = m.name;
        connect(m_mgr, &ModelManager::downloadProgress, page,
            [progressLabel, modelName](const QString& n, int pct) {
                if (n == modelName) progressLabel->setText(QString("%1%").arg(pct));
            });
        connect(m_mgr, &ModelManager::downloadFinished, page,
            [progressLabel, modelName](const QString& n, bool ok) {
                if (n == modelName) progressLabel->setText(ok ? "\u2713 Done" : "\u2717 Failed");
            });

        reqLayout->addLayout(row);
    }
    layout->addWidget(reqGroup);

    // ── Optional Models ──────────────────────────────────────────────────────
    auto* optGroup = new QGroupBox("Optional Models (select to download)", page);
    auto* optLayout = new QVBoxLayout(optGroup);

    for (const auto& m : MODELS) {
        if (m.required) continue;

        auto* row = new QHBoxLayout;
        auto* cb = new QCheckBox(
            QString("%1  (%2 GB) \u2014 %3").arg(m.label).arg(m.gb, 0, 'f', 1).arg(m.note),
            optGroup);
        cb->setChecked(false);
        cb->setObjectName("aboutDesc");
        row->addWidget(cb);
        row->addStretch();

        auto* progressLabel = new QLabel(optGroup);
        progressLabel->setObjectName("aiDailyCounter");
        progressLabel->setFixedWidth(80);
        row->addWidget(progressLabel);

        const QString modelName = m.name;
        optionalChecks.append({modelName, cb});

        connect(m_mgr, &ModelManager::downloadProgress, page,
            [progressLabel, modelName](const QString& n, int pct) {
                if (n == modelName) progressLabel->setText(QString("%1%").arg(pct));
            });
        connect(m_mgr, &ModelManager::downloadFinished, page,
            [progressLabel, modelName, cb](const QString& n, bool ok) {
                if (n == modelName) {
                    progressLabel->setText(ok ? "\u2713 Done" : "\u2717 Failed");
                    if (ok) { cb->setChecked(true); cb->setEnabled(false); }
                }
            });

        optLayout->addLayout(row);
    }

    auto* optNote = new QLabel(
        "<i>Optional models enable offline generation without cloud APIs. "
        "You can also download these later from the Model Manager.</i>", optGroup);
    optNote->setWordWrap(true);
    optNote->setTextFormat(Qt::RichText);
    optNote->setObjectName("aiDailyCounter");
    optLayout->addWidget(optNote);

    layout->addWidget(optGroup);

    // ── Download button ──────────────────────────────────────────────────────
    auto* downloadBtn = new QPushButton(
        "\u2193  Download Selected Models", page);
    downloadBtn->setObjectName("aiGenerateBtn");
    downloadBtn->setMinimumHeight(38);
    connect(downloadBtn, &QPushButton::clicked, page,
        [this, downloadBtn, optionalChecks]() {
            m_mgr->downloadRecommendedModels();
            for (const auto& [name, cb] : optionalChecks) {
                if (cb->isChecked())
                    m_mgr->downloadModel(name);
            }
            downloadBtn->setEnabled(false);
            downloadBtn->setText(
                "\u23f3  Downloading in background \u2014 you can continue setup \u2026");
        });
    layout->addWidget(downloadBtn);

    auto* skipNote = new QLabel(
        "<i>Or skip downloads and use cloud APIs instead.</i>", page);
    skipNote->setWordWrap(true);
    skipNote->setTextFormat(Qt::RichText);
    skipNote->setObjectName("aiDailyCounter");
    layout->addWidget(skipNote);

    layout->addStretch();
    addPage(page);
}

void OnboardingWizard::buildApiKeysPage()
{
    auto* page = new QWizardPage;
    page->setTitle("Configure API Keys");
    page->setSubTitle("Optional: add your API keys to enable AI cloud features.");

    auto* layout = new QVBoxLayout(page);
    layout->setSpacing(12);

    auto* intro = new QLabel(
        "<p>Wavy Labs is free and open-source — you bring your own API keys. "
        "Keys are stored encrypted on your machine and never sent to Wavy Labs servers.</p>"
        "<p>You can skip this step and add keys later from <b>Edit \u2192 Settings</b>.</p>",
        page);
    intro->setWordWrap(true);
    intro->setTextFormat(Qt::RichText);
    intro->setObjectName("aboutDesc");
    layout->addWidget(intro);

    auto* group = new QGroupBox("Cloud API Keys", page);
    auto* form  = new QFormLayout(group);
    form->setSpacing(10);
    form->setLabelAlignment(Qt::AlignRight);

    auto makeRow = [&](QLineEdit*& edit, const QString& placeholder,
                       const QString& url, QGroupBox* parent) {
        edit = new QLineEdit(parent);
        edit->setEchoMode(QLineEdit::Password);
        edit->setPlaceholderText(placeholder);
        edit->setClearButtonEnabled(true);
        edit->setObjectName("promptBarInput");

        auto* row = new QHBoxLayout;
        row->addWidget(edit, 1);
        auto* lnk = new QLabel(
            QString("<a href='%1'>Get key</a>").arg(url), parent);
        lnk->setOpenExternalLinks(true);
        lnk->setObjectName("aiDailyCounter");
        row->addWidget(lnk);
        return row;
    };

    form->addRow("Anthropic (Claude):",
        makeRow(m_anthropicEdit, "sk-ant-\u2026",
                "https://console.anthropic.com/settings/keys", group));
    form->addRow("Groq (free tier):",
        makeRow(m_groqEdit, "gsk_\u2026",
                "https://console.groq.com/keys", group));
    form->addRow("ElevenLabs (voice/music):",
        makeRow(m_elevenLabsEdit, "sk_\u2026",
                "https://elevenlabs.io/app/settings/api-keys", group));

    // Pre-fill any previously saved keys
    m_anthropicEdit->setText(ApiKeySettings::loadKey("anthropic"));
    m_groqEdit->setText(ApiKeySettings::loadKey("groq"));
    m_elevenLabsEdit->setText(ApiKeySettings::loadKey("elevenlabs"));

    layout->addWidget(group);

    // Save & Continue button (wizard Next also works — keys save on page leave)
    auto* saveBtn = new QPushButton("\u2713  Save & Continue", page);
    saveBtn->setObjectName("aiGenerateBtn");
    saveBtn->setMinimumHeight(36);
    connect(saveBtn, &QPushButton::clicked, page, [this, saveBtn]() {
        // Encrypt and persist all three keys
        QSettings ks("WavyLabs", "ApiKeys");
        const QList<QPair<QString, QLineEdit*>> fields = {
            {"anthropic",  m_anthropicEdit},
            {"groq",       m_groqEdit},
            {"elevenlabs", m_elevenLabsEdit},
        };
        QVariantMap rpcParams;
        for (const auto& [key, edit] : fields) {
            const QString val = edit->text().trimmed();
            ks.setValue(key, LicenseManager::encryptApiKey(val));
            if (!val.isEmpty())
                rpcParams[key] = val;
        }
        // Push live to running backend (best-effort)
        if (!rpcParams.isEmpty()) {
            AIClient::instance()->callAsync("update_api_keys", rpcParams,
                [](bool, const QVariantMap&) {});
        }
        saveBtn->setText("\u2713 Saved!");
        saveBtn->setEnabled(false);
    });
    layout->addWidget(saveBtn);
    layout->addStretch();

    addPage(page);
}

void OnboardingWizard::buildFinishPage()
{
    auto* page = new QWizardPage;
    page->setTitle("You're all set!");
    page->setSubTitle("Start making music with AI.");

    auto* layout = new QVBoxLayout(page);
    auto* tips = new QLabel(
        "<p><b>Quick start tips:</b></p>"
        "<ul>"
        "  <li>Click <b>\u26a1 AI</b> in the toolbar (or press <b>F9</b>) to open the AI Panel</li>"
        "  <li>Type a music description and press <b>Generate</b></li>"
        "  <li>Right-click any audio clip and choose <b>Split Stems</b></li>"
        "  <li>Press <b>Ctrl+K</b> to use natural-language Prompt Commands</li>"
        "  <li>Add or update API keys anytime from <b>Edit \u2192 Settings</b></li>"
        "</ul>"
        "<p>Need help? Visit <a href='https://github.com/stroland02/Wavy-Labs-Code-Base-' "
        "style='color:#4fc3f7'>github.com/stroland02/Wavy-Labs-Code-Base-</a></p>",
        page);
    tips->setTextFormat(Qt::RichText);
    tips->setWordWrap(true);
    tips->setOpenExternalLinks(true);
    layout->addWidget(tips);
    layout->addStretch();

    addPage(page);
}
