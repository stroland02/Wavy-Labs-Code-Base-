#pragma once
#include <QWizard>
#include <QLabel>
#include <QCheckBox>
#include <QLineEdit>
#include <QPushButton>

class ModelManager;
class ModelManagerPanel;

// ---------------------------------------------------------------------------
// OnboardingWizard — shown on first launch.
// Pages: Welcome → Model Download → API Keys → Finish
// ---------------------------------------------------------------------------

class OnboardingWizard : public QWizard
{
    Q_OBJECT
public:
    explicit OnboardingWizard(ModelManager* mgr, QWidget* parent = nullptr);

    // Returns true if the wizard should be shown (first run).
    static bool shouldShow();
    // Mark as completed so it won't show again.
    static void markCompleted();

private:
    void buildWelcomePage();
    void buildCloudPage();
    void buildApiKeysPage();
    void buildFinishPage();

    ModelManager* m_mgr{nullptr};
    QLabel*       m_cloudStatusLabel{nullptr};

    // ── API Keys page ─────────────────────────────────────────────────────
    QLineEdit*   m_anthropicEdit{nullptr};
    QLineEdit*   m_groqEdit{nullptr};
    QLineEdit*   m_elevenLabsEdit{nullptr};
};
