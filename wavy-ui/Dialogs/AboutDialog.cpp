#include "AboutDialog.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QDialogButtonBox>
#include <QFont>
#include <QSvgWidget>
#include <QDesktopServices>
#include <QUrl>

#ifndef WAVY_VERSION
#define WAVY_VERSION "1.0.0"
#endif

AboutDialog::AboutDialog(QWidget* parent)
    : QDialog(parent)
{
    setWindowTitle("About Wavy Labs");
    setFixedSize(480, 360);
    setObjectName("aboutDialog");

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(32, 28, 32, 20);
    root->setSpacing(12);

    // Logo + app name row
    auto* topRow = new QHBoxLayout;
    auto* logo = new QSvgWidget(":/icons/wavy-labs.svg", this);
    logo->setFixedSize(56, 56);
    topRow->addWidget(logo);
    topRow->addSpacing(16);

    auto* nameCol = new QVBoxLayout;
    auto* nameLabel = new QLabel("Wavy Labs", this);
    QFont nf = nameLabel->font();
    nf.setPointSize(18); nf.setBold(true);
    nameLabel->setFont(nf);
    nameLabel->setObjectName("aiPanelTitle");

    auto* verLabel = new QLabel(
        QString("Version %1 — AI-Powered DAW").arg(WAVY_VERSION), this);
    verLabel->setObjectName("aiDailyCounter");

    nameCol->addWidget(nameLabel);
    nameCol->addWidget(verLabel);
    nameCol->setSpacing(2);
    topRow->addLayout(nameCol);
    topRow->addStretch();
    root->addLayout(topRow);

    // Description
    auto* desc = new QLabel(
        "Wavy Labs is a free, open-source AI-powered Digital Audio Workstation\n"
        "forked from LMMS. All AI features run 100% locally — your music stays yours.",
        this);
    desc->setWordWrap(true);
    desc->setObjectName("aboutDesc");
    root->addWidget(desc);

    // Separator
    auto* sep = new QFrame(this);
    sep->setFrameShape(QFrame::HLine);
    sep->setObjectName("separator");
    root->addWidget(sep);

    // Credits grid
    auto* grid = new QVBoxLayout;
    grid->setSpacing(4);
    auto addRow = [&](const QString& key, const QString& val) {
        auto* row = new QHBoxLayout;
        auto* k = new QLabel(key + ":", this);
        k->setObjectName("aiDailyCounter");
        k->setFixedWidth(110);
        k->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
        auto* v = new QLabel(val, this);
        v->setWordWrap(true);
        row->addWidget(k);
        row->addSpacing(8);
        row->addWidget(v, 1);
        grid->addLayout(row);
    };
    addRow("Built on",    "LMMS (GPL-2.0) by the LMMS contributors");
    addRow("AI models",   "ElevenLabs, Anthropic Claude, Demucs v4, ACE-Step, DiffRhythm");
    addRow("License",     "GNU General Public License v2.0");
    addRow("Website",     "<a href='https://wavylab.net' style='color:#4fc3f7'>wavylab.net</a>");
    addRow("Source",      "<a href='https://github.com/wavylabs/wavy-labs' "
                          "style='color:#4fc3f7'>github.com/wavylabs/wavy-labs</a>");
    root->addLayout(grid);

    // Make links clickable
    const auto labels = findChildren<QLabel*>();
    for (auto* l : labels) {
        if (l->text().contains("<a "))
            l->setOpenExternalLinks(true);
    }

    root->addStretch();

    // Buttons
    auto* btns = new QDialogButtonBox(QDialogButtonBox::Ok, this);
    btns->button(QDialogButtonBox::Ok)->setObjectName("aiGenerateBtn");
    connect(btns, &QDialogButtonBox::accepted, this, &QDialog::accept);
    root->addWidget(btns);
}
