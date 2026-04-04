#pragma once
#include <QWidget>
#include <QLineEdit>
#include <QLabel>
#include <QPushButton>
#include <QVariantMap>

#include "../LicenseGate/LicenseManager.h"

class AIClient;

// ---------------------------------------------------------------------------
// PromptBar — always-visible natural-language command bar (Cmd+K / Ctrl+K)
// Maps parsed actions to LMMS Engine API calls via EngineAPI.
// Studio tier required — shows a lock badge for Free/Pro users.
// ---------------------------------------------------------------------------

class PromptBar : public QWidget
{
    Q_OBJECT
public:
    explicit PromptBar(AIClient* client, QWidget* parent = nullptr);

    // Provide current DAW context so the LLM can give relevant responses.
    void setDawContext(const QVariantMap& ctx) { m_dawContext = ctx; }

Q_SIGNALS:
    // Emitted with the parsed list of action objects.
    // Connect to EngineAPI::dispatchActions() on the LMMS side.
    void actionsReady(const QVariantList& actions);

private Q_SLOTS:
    void onSubmit();
    void onCommandFinished(bool ok, const QVariantMap& result);
    void onTierChanged(Tier newTier);

private:
    void buildUI();
    void setBusy(bool busy);
    void updateTierBadge(Tier t);

    AIClient*    m_client{nullptr};
    QLineEdit*   m_input{nullptr};
    QPushButton* m_submitBtn{nullptr};
    QLabel*      m_statusLabel{nullptr};
    QLabel*      m_tierBadge{nullptr};
    QVariantMap  m_dawContext;
};
