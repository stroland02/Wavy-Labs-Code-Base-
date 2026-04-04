#include "ApiKeySettings.h"
#include "LicenseManager.h"
#include "../IPC/AIClient.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QFormLayout>
#include <QGroupBox>
#include <QLabel>
#include <QPushButton>
#include <QSettings>
#include <QDialogButtonBox>
#include <QToolButton>

// ---------------------------------------------------------------------------
// Static helper
// ---------------------------------------------------------------------------

QString ApiKeySettings::loadKey(const QString& name)
{
    QSettings ks("WavyLabs", "ApiKeys");
    return LicenseManager::decryptApiKey(ks.value(name).toByteArray());
}

// ---------------------------------------------------------------------------
// Construction
// ---------------------------------------------------------------------------

ApiKeySettings::ApiKeySettings(QWidget* parent)
    : QDialog(parent)
{
    setWindowTitle("API Key Settings");
    setObjectName("apiKeySettings");
    setMinimumWidth(520);
    buildUi();
}

// ---------------------------------------------------------------------------
// UI
// ---------------------------------------------------------------------------

static QLineEdit* makeKeyEdit(const QString& placeholder, QWidget* parent)
{
    auto* edit = new QLineEdit(parent);
    edit->setEchoMode(QLineEdit::Password);
    edit->setPlaceholderText(placeholder);
    edit->setClearButtonEnabled(true);
    edit->setObjectName("promptBarInput");

    // Show/hide toggle button (appended to line edit via layout trick)
    return edit;
}

void ApiKeySettings::buildUi()
{
    auto* layout = new QVBoxLayout(this);
    layout->setSpacing(12);

    // ── Header ──────────────────────────────────────────────────────────────
    auto* header = new QLabel(
        "<p><b>API Keys</b> — Wavy Labs is free and open-source. "
        "Add your own API keys to enable AI features.</p>"
        "<p>Keys are stored encrypted on your machine and never sent to Wavy Labs servers.</p>",
        this);
    header->setWordWrap(true);
    header->setTextFormat(Qt::RichText);
    header->setObjectName("aboutDesc");
    layout->addWidget(header);

    // ── Keys form ──────────────────────────────────────────────────────────
    auto* group = new QGroupBox("Cloud API Keys", this);
    auto* form  = new QFormLayout(group);
    form->setSpacing(10);
    form->setLabelAlignment(Qt::AlignRight);

    // Anthropic
    m_anthropicEdit = makeKeyEdit("sk-ant-…", group);
    auto* anthropicRow = new QHBoxLayout;
    anthropicRow->addWidget(m_anthropicEdit, 1);
    auto* anthropicLink = new QLabel(
        "<a href='https://console.anthropic.com/settings/keys'>Get key</a>", group);
    anthropicLink->setOpenExternalLinks(true);
    anthropicLink->setObjectName("aiDailyCounter");
    anthropicRow->addWidget(anthropicLink);
    form->addRow("Anthropic (Claude):", anthropicRow);

    // Groq
    m_groqEdit = makeKeyEdit("gsk_…", group);
    auto* groqRow = new QHBoxLayout;
    groqRow->addWidget(m_groqEdit, 1);
    auto* groqLink = new QLabel(
        "<a href='https://console.groq.com/keys'>Get key</a>", group);
    groqLink->setOpenExternalLinks(true);
    groqLink->setObjectName("aiDailyCounter");
    groqRow->addWidget(groqLink);
    form->addRow("Groq (free tier):", groqRow);

    // ElevenLabs
    m_elevenLabsEdit = makeKeyEdit("sk_…", group);
    auto* elRow = new QHBoxLayout;
    elRow->addWidget(m_elevenLabsEdit, 1);
    auto* elLink = new QLabel(
        "<a href='https://elevenlabs.io/app/settings/api-keys'>Get key</a>", group);
    elLink->setOpenExternalLinks(true);
    elLink->setObjectName("aiDailyCounter");
    elRow->addWidget(elLink);
    form->addRow("ElevenLabs (voice/music):", elRow);

    // Freesound
    m_freesoundEdit = makeKeyEdit("Freesound API key", group);
    auto* fsRow = new QHBoxLayout;
    fsRow->addWidget(m_freesoundEdit, 1);
    auto* fsLink = new QLabel(
        "<a href='https://freesound.org/apiv2/apply'>Get key</a>", group);
    fsLink->setOpenExternalLinks(true);
    fsLink->setObjectName("aiDailyCounter");
    fsRow->addWidget(fsLink);
    form->addRow("Freesound (optional):", fsRow);

    layout->addWidget(group);

    // ── Load existing (decrypted) values ────────────────────────────────────
    m_anthropicEdit->setText(loadKey("anthropic"));
    m_groqEdit->setText(loadKey("groq"));
    m_elevenLabsEdit->setText(loadKey("elevenlabs"));
    m_freesoundEdit->setText(loadKey("freesound"));

    // ── Buttons ─────────────────────────────────────────────────────────────
    auto* btnBox = new QDialogButtonBox(
        QDialogButtonBox::Save | QDialogButtonBox::Cancel, this);
    btnBox->button(QDialogButtonBox::Save)->setObjectName("aiGenerateBtn");
    connect(btnBox, &QDialogButtonBox::accepted, this, &ApiKeySettings::save);
    connect(btnBox, &QDialogButtonBox::rejected, this, &QDialog::reject);
    layout->addWidget(btnBox);
}

// ---------------------------------------------------------------------------
// Save
// ---------------------------------------------------------------------------

void ApiKeySettings::save()
{
    QSettings ks("WavyLabs", "ApiKeys");

    const QStringList names = {"anthropic", "groq", "elevenlabs", "freesound"};
    const QList<QLineEdit*> edits = {
        m_anthropicEdit, m_groqEdit, m_elevenLabsEdit, m_freesoundEdit
    };

    QVariantMap rpcParams;
    for (int i = 0; i < names.size(); ++i) {
        const QString val = edits[i]->text().trimmed();
        ks.setValue(names[i], LicenseManager::encryptApiKey(val));
        if (!val.isEmpty())
            rpcParams[names[i]] = val;
    }

    // Push live to running backend (best-effort — backend may not be up yet)
    if (!rpcParams.isEmpty()) {
        AIClient::instance()->callAsync("update_api_keys", rpcParams,
            [](bool, const QVariantMap&) {});
    }

    accept();
}
