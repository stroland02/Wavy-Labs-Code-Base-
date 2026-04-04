#pragma once
#include <QDialog>
#include <QLineEdit>
#include <QPushButton>
#include <QLabel>

// ---------------------------------------------------------------------------
// ApiKeySettings — settings dialog for user-supplied API keys.
// Keys are stored encrypted (DPAPI on Windows) via QSettings("WavyLabs","ApiKeys").
// On Save, keys are injected into the running Python backend via RPC.
// ---------------------------------------------------------------------------

class ApiKeySettings : public QDialog
{
    Q_OBJECT
public:
    explicit ApiKeySettings(QWidget* parent = nullptr);

    // Convenience: load decrypted key values for a given settings key name.
    static QString loadKey(const QString& name);

private:
    void buildUi();
    void save();

    QLineEdit* m_anthropicEdit{nullptr};
    QLineEdit* m_groqEdit{nullptr};
    QLineEdit* m_elevenLabsEdit{nullptr};
    QLineEdit* m_freesoundEdit{nullptr};
};
