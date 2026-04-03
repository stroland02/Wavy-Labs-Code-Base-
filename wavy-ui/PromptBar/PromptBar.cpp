#include "PromptBar.h"
#include "../IPC/AIClient.h"
#include "../LicenseGate/LicenseManager.h"

#include <QHBoxLayout>
#include <QKeySequence>
#include <QShortcut>
#include <QSizePolicy>
#include <QStyle>
#include <QFont>

PromptBar::PromptBar(AIClient* client, QWidget* parent)
    : QWidget(parent), m_client(client)
{
    buildUI();

    // Update badge and gate when license tier changes
    connect(LicenseManager::instance(), &LicenseManager::tierChanged,
            this, &PromptBar::onTierChanged);

    // Ctrl+K / Cmd+K to focus prompt bar
    auto* shortcut = new QShortcut(QKeySequence("Ctrl+K"), this);
    connect(shortcut, &QShortcut::activated, m_input, [this]() {
        m_input->setFocus();
        m_input->selectAll();
    });
}

void PromptBar::buildUI()
{
    setObjectName("promptBarWidget");
    setFixedHeight(44);

    auto* layout = new QHBoxLayout(this);
    layout->setContentsMargins(12, 4, 12, 4);
    layout->setSpacing(8);

    // Wavy icon label
    auto* icon = new QLabel("\u2726", this);
    icon->setObjectName("promptBarIcon");
    QFont f = icon->font();
    f.setPointSize(14);
    icon->setFont(f);
    layout->addWidget(icon);

    m_input = new QLineEdit(this);
    m_input->setObjectName("promptBarInput");
    m_input->setPlaceholderText(
        "Ask Wavy Labs anything \u2026 (Ctrl+K)  "
        "e.g. \"Add a 4-bar drum loop at 120 BPM\"");
    m_input->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    connect(m_input, &QLineEdit::returnPressed, this, &PromptBar::onSubmit);
    layout->addWidget(m_input);

    m_submitBtn = new QPushButton("Send", this);
    m_submitBtn->setObjectName("promptBarSend");
    m_submitBtn->setFixedWidth(60);
    connect(m_submitBtn, &QPushButton::clicked, this, &PromptBar::onSubmit);
    layout->addWidget(m_submitBtn);

    m_statusLabel = new QLabel(this);
    m_statusLabel->setObjectName("promptBarStatus");
    m_statusLabel->setFixedWidth(80);
    layout->addWidget(m_statusLabel);

    // Tier badge — updated dynamically by onTierChanged()
    m_tierBadge = new QLabel(this);
    layout->addWidget(m_tierBadge);

    // Set initial badge state from current tier
    updateTierBadge(LicenseManager::instance()->tier());
}

void PromptBar::updateTierBadge(Tier t)
{
    if (t == Tier::Studio) {
        m_tierBadge->setText("Studio");
        m_tierBadge->setObjectName("tierBadgeStudio");
        m_tierBadge->setToolTip("Prompt Commands — Studio tier active");
        m_input->setEnabled(true);
        m_submitBtn->setEnabled(true);
    } else {
        const QString plan = (t == Tier::Pro) ? "Pro" : "Free";
        m_tierBadge->setText("\U0001f512 Studio only");
        m_tierBadge->setObjectName("tierBadgeLocked");
        m_tierBadge->setToolTip(
            QString("Prompt Commands require Studio ($24.99/mo). "
                    "Current plan: %1").arg(plan));
        // Input stays visible but submit will show the gate message
    }
    // Force style refresh
    m_tierBadge->style()->unpolish(m_tierBadge);
    m_tierBadge->style()->polish(m_tierBadge);
}

void PromptBar::onTierChanged(Tier newTier)
{
    updateTierBadge(newTier);
    // Clear any stale status from a previous tier state
    m_statusLabel->clear();
}

void PromptBar::onSubmit()
{
    const QString text = m_input->text().trimmed();
    if (text.isEmpty()) return;

    // Studio-only gate
    if (!LicenseManager::instance()->canPromptCmd()) {
        m_statusLabel->setText("\U0001f512 Studio");
        m_statusLabel->setToolTip(
            "Prompt Commands require an Anthropic or Groq API key. "
            "Configure keys in Edit → Settings.");
        return;
    }

    setBusy(true);

    m_client->promptCommand(text, m_dawContext, QVariantList{},
        [this](bool ok, const QVariantMap& result) {
            QMetaObject::invokeMethod(this, [this, ok, result]() {
                onCommandFinished(ok, result);
            }, Qt::QueuedConnection);
        });
}

void PromptBar::onCommandFinished(bool ok, const QVariantMap& result)
{
    setBusy(false);
    if (!ok) {
        m_statusLabel->setText("\u26a0 Error");
        m_statusLabel->setToolTip(result.value("error").toString());
        return;
    }

    const QVariantList actions = result.value("actions").toList();
    const QString explanation  = result.value("explanation").toString();

    m_statusLabel->setText("\u2713 Done");
    m_statusLabel->setToolTip(explanation);
    m_input->clear();

    emit actionsReady(actions);
}

void PromptBar::setBusy(bool busy)
{
    m_input->setEnabled(!busy);
    m_submitBtn->setEnabled(!busy);
    m_statusLabel->setText(busy ? "\u23f3 \u2026" : "");
}
