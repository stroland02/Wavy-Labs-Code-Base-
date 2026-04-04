#pragma once

#include <QCheckBox>
#include <QDialog>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QStackedWidget>

class LicenseManager;

// ---------------------------------------------------------------------------
// LoginDialog — Account settings dialog.
//
// Shows account info panel when already signed in (email, tier, sign-out).
// Shows sign-in form when not signed in (email, password, remember me).
// ---------------------------------------------------------------------------

class LoginDialog : public QDialog
{
    Q_OBJECT

public:
    explicit LoginDialog(LicenseManager* licenseManager,
                         QWidget*        parent = nullptr);

Q_SIGNALS:
    void loginSucceeded(const QString& email, const QString& tier);

private Q_SLOTS:
    void onSignIn();
    void onSignOut();

private:
    void setStatus(const QString& msg, bool isError);
    void buildSignInPage();
    void buildAccountPage();
    void showPage(int index);

    LicenseManager*  m_lm{nullptr};
    QStackedWidget*  m_stack{nullptr};

    // Sign-in page
    QLineEdit*   m_emailEdit{nullptr};
    QLineEdit*   m_passEdit{nullptr};
    QCheckBox*   m_rememberChk{nullptr};
    QPushButton* m_signInBtn{nullptr};
    QLabel*      m_statusLabel{nullptr};

    // Account page
    QLabel*      m_acctEmail{nullptr};
    QLabel*      m_acctTier{nullptr};
    QPushButton* m_signOutBtn{nullptr};
};
