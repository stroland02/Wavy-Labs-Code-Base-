#include "LoginDialog.h"
#include "LicenseManager.h"

#include <QFormLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QSettings>
#include <QThread>
#include <QTimer>
#include <QVBoxLayout>

static constexpr const char* SETTINGS_REMEMBER_EMAIL = "account/remembered_email";
static constexpr const char* SETTINGS_REMEMBER_ME    = "account/remember_me";

LoginDialog::LoginDialog(LicenseManager* lm, QWidget* parent)
    : QDialog(parent)
    , m_lm(lm)
{
    setMinimumWidth(420);
    setModal(true);
    setObjectName("loginDialog");

    m_stack = new QStackedWidget(this);

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->addWidget(m_stack);

    buildSignInPage();   // index 0
    buildAccountPage();  // index 1

    // Show the right page immediately
    showPage(m_lm && m_lm->isLoggedIn() ? 1 : 0);
}

// ── Sign-in page ─────────────────────────────────────────────────────────────

void LoginDialog::buildSignInPage()
{
    auto* page = new QWidget;
    auto* root = new QVBoxLayout(page);
    root->setContentsMargins(32, 28, 32, 24);
    root->setSpacing(14);

    auto* title = new QLabel("Sign in to Wavy Labs", page);
    QFont tf = title->font();
    tf.setPointSize(15);
    tf.setBold(true);
    title->setFont(tf);
    root->addWidget(title);

    auto* sub = new QLabel(
        "Your subscription tier is managed at "
        "<a href='https://wavylab.net'>wavylab.net</a>.", page);
    sub->setWordWrap(true);
    sub->setOpenExternalLinks(true);
    sub->setObjectName("aiDailyCounter");
    root->addWidget(sub);

    root->addSpacing(4);

    // Form
    auto* form = new QFormLayout;
    form->setSpacing(10);

    m_emailEdit = new QLineEdit(page);
    m_emailEdit->setPlaceholderText("your@email.com");
    m_emailEdit->setClearButtonEnabled(true);
    form->addRow("Email:", m_emailEdit);

    m_passEdit = new QLineEdit(page);
    m_passEdit->setEchoMode(QLineEdit::Password);
    m_passEdit->setPlaceholderText("Password");
    form->addRow("Password:", m_passEdit);

    root->addLayout(form);

    // Remember me
    m_rememberChk = new QCheckBox("Remember me", page);
    root->addWidget(m_rememberChk);

    // Pre-fill from saved settings
    QSettings s("WavyLabs", "App");
    const bool rememberMe = s.value(SETTINGS_REMEMBER_ME, false).toBool();
    m_rememberChk->setChecked(rememberMe);
    if (rememberMe)
        m_emailEdit->setText(s.value(SETTINGS_REMEMBER_EMAIL, "").toString());

    // Sign-in button
    m_signInBtn = new QPushButton("Sign in \u2192", page);
    m_signInBtn->setObjectName("aiGenerateBtn");
    m_signInBtn->setMinimumHeight(38);
    root->addWidget(m_signInBtn);

    // Status
    m_statusLabel = new QLabel(page);
    m_statusLabel->setWordWrap(true);
    m_statusLabel->setMinimumHeight(20);
    root->addWidget(m_statusLabel);

    root->addStretch();

    // Footer links
    auto* footer = new QHBoxLayout;
    auto* forgotLnk = new QLabel(
        "<a href='https://wavylab.net/forgot-password'>Forgot password?</a>", page);
    forgotLnk->setOpenExternalLinks(true);
    forgotLnk->setObjectName("aiDailyCounter");
    auto* signupLnk = new QLabel(
        "No account? <a href='https://wavylab.net'>Sign up</a>", page);
    signupLnk->setOpenExternalLinks(true);
    signupLnk->setObjectName("aiDailyCounter");
    footer->addWidget(forgotLnk);
    footer->addStretch();
    footer->addWidget(signupLnk);
    root->addLayout(footer);

    connect(m_signInBtn, &QPushButton::clicked, this, &LoginDialog::onSignIn);
    connect(m_emailEdit, &QLineEdit::returnPressed, this, &LoginDialog::onSignIn);
    connect(m_passEdit,  &QLineEdit::returnPressed, this, &LoginDialog::onSignIn);

    m_stack->addWidget(page);   // index 0
}

// ── Account info page ─────────────────────────────────────────────────────────

void LoginDialog::buildAccountPage()
{
    auto* page = new QWidget;
    auto* root = new QVBoxLayout(page);
    root->setContentsMargins(32, 28, 32, 24);
    root->setSpacing(16);

    auto* title = new QLabel("Account Settings", page);
    QFont tf = title->font();
    tf.setPointSize(15);
    tf.setBold(true);
    title->setFont(tf);
    root->addWidget(title);

    root->addSpacing(4);

    // Email row
    auto* emailRow = new QHBoxLayout;
    auto* emailIcon = new QLabel("\u2709", page);  // ✉
    emailIcon->setFixedWidth(24);
    m_acctEmail = new QLabel(page);
    m_acctEmail->setObjectName("aiDailyCounter");
    emailRow->addWidget(emailIcon);
    emailRow->addWidget(m_acctEmail, 1);
    root->addLayout(emailRow);

    // Tier row
    auto* tierRow = new QHBoxLayout;
    auto* tierIcon = new QLabel("\u25C6", page);  // ◆
    tierIcon->setFixedWidth(24);
    tierIcon->setStyleSheet("color: #9c5cbf; font-size: 14px;");
    m_acctTier = new QLabel(page);
    QFont tierFont = m_acctTier->font();
    tierFont.setBold(true);
    tierFont.setPointSize(12);
    m_acctTier->setFont(tierFont);
    tierRow->addWidget(tierIcon);
    tierRow->addWidget(m_acctTier, 1);
    root->addLayout(tierRow);

    root->addSpacing(8);

    // Manage account link
    auto* manageLnk = new QLabel(
        "<a href='https://wavylab.net/dashboard'>Manage subscription at wavylab.net</a>", page);
    manageLnk->setOpenExternalLinks(true);
    manageLnk->setObjectName("aiDailyCounter");
    root->addWidget(manageLnk);

    root->addStretch();

    // Sign out button
    m_signOutBtn = new QPushButton("Sign out", page);
    m_signOutBtn->setMinimumHeight(36);
    m_signOutBtn->setStyleSheet("QPushButton { color: #e05a5a; border: 1px solid #e05a5a; }");
    root->addWidget(m_signOutBtn);

    connect(m_signOutBtn, &QPushButton::clicked, this, &LoginDialog::onSignOut);

    m_stack->addWidget(page);   // index 1
}

// ── Page switching ────────────────────────────────────────────────────────────

void LoginDialog::showPage(int index)
{
    if (index == 1 && m_lm) {
        // Populate account info
        m_acctEmail->setText(m_lm->currentEmail());

        const Tier t = m_lm->tier();
        const QString tierName = t == Tier::Studio ? "Studio" :
                                 t == Tier::Pro    ? "Pro"    : "Free";
        const QString tierColor = t == Tier::Studio ? "#9c5cbf" :
                                  t == Tier::Pro    ? "#4fc3f7" : "#aaaaaa";
        m_acctTier->setText(tierName + " Plan");
        m_acctTier->setStyleSheet(QString("color: %1;").arg(tierColor));

        setWindowTitle("Account Settings");
    } else {
        setWindowTitle("Sign in to Wavy Labs");
    }
    m_stack->setCurrentIndex(index);
}

// ── Slots ─────────────────────────────────────────────────────────────────────

void LoginDialog::onSignIn()
{
    if (!m_lm) {
        setStatus("\u2717  License manager not available.", true);
        return;
    }

    const QString email = m_emailEdit->text().trimmed();
    const QString pass  = m_passEdit->text();

    if (email.isEmpty() || pass.isEmpty()) {
        setStatus("\u2717  Please enter your email and password.", true);
        return;
    }

    m_signInBtn->setEnabled(false);
    m_signInBtn->setText("Signing in\u2026");
    setStatus("", false);

    // Run login on background thread to avoid blocking the UI
    auto* lm = m_lm;
    const bool rememberMe = m_rememberChk->isChecked();
    QThread* t = QThread::create([this, lm, email, pass, rememberMe]() {
        const bool ok = lm->loginWithAccount(email, pass);
        QMetaObject::invokeMethod(this, [this, ok, email, rememberMe, lm]() {
            m_signInBtn->setEnabled(true);
            m_signInBtn->setText("Sign in \u2192");

            if (ok) {
                QSettings s("WavyLabs", "App");
                s.setValue(SETTINGS_REMEMBER_ME, rememberMe);
                s.setValue(SETTINGS_REMEMBER_EMAIL,
                           rememberMe ? email : QString());

                const Tier tier = lm->tier();
                const QString tierName = tier == Tier::Studio ? "Studio" :
                                         tier == Tier::Pro    ? "Pro"    : "Free";
                emit loginSucceeded(email, tierName.toLower());
                showPage(1);
            } else {
                setStatus(
                    "\u2717  Incorrect email or password, or account not found.\n"
                    "Check your credentials at wavylab.net.", true);
            }
        }, Qt::QueuedConnection);
    });
    connect(t, &QThread::finished, t, &QObject::deleteLater);
    t->start();
}

void LoginDialog::onSignOut()
{
    if (m_lm) m_lm->logoutAccount();

    // Clear remembered password (keep email if remember-me was on)
    QSettings s("WavyLabs", "App");
    if (!s.value(SETTINGS_REMEMBER_ME, false).toBool())
        s.remove(SETTINGS_REMEMBER_EMAIL);

    m_passEdit->clear();
    setStatus("", false);
    showPage(0);
}

void LoginDialog::setStatus(const QString& msg, bool isError)
{
    m_statusLabel->setText(msg);
    m_statusLabel->setStyleSheet(isError ? "color: #e05a5a;" : "color: #4fc3f7;");
}
