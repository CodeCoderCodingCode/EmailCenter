"""Local Qt render evidence for language and scale; no project or Gmail access."""
import argparse,json,os,time,sys
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QEvent
from PySide6.QtGui import QFontDatabase,QAction
from PySide6.QtWidgets import QApplication,QWidget,QComboBox,QTableWidget,QListWidget
from emailcenter.language import Message,TEXTS,EXTRA_TEXTS,TEMPLATES,render,translate_tree,set_language,translate
from emailcenter.preferences import Preferences,PreferencesStore
from emailcenter.ui.main_window import MainWindow
from emailcenter.ui.record_dialogs import RecordDialog
from emailcenter.ui.project_wizard import ProjectWizard
from emailcenter.ui.localization import SOURCE_ROLE


def capture(scale,output):
    output.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
    font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/segoeui.ttf'
    if not QFontDatabase.families() and font.is_file():QFontDatabase.addApplicationFont(str(font))
    with TemporaryDirectory(dir=ROOT,prefix='localization-render-') as tmp:
        store=PreferencesStore(Path(tmp)/'preferences.json');store.load()
        store.save(Preferences(language='en',reduced_motion=True))
        window=MainWindow(settings_store=store);window.resize(1000,720);window.show();window.navigate('settings');app.processEvents()
        missing=set();sources=set()
        def check(source):
            if isinstance(source,Message):
                sources.add((source.source,source.template))
                catalog=TEMPLATES if source.template else {**TEXTS,**EXTRA_TEXTS}
                if source.source not in catalog and any(c.isalpha() for c in source.source):missing.add(source.source)
                for value in source.arguments:
                    if isinstance(value,Message):check(value)
        def inventory(root):
            for widget in [root,*root.findChildren(QWidget),*root.findChildren(QAction)]:
                for prop in widget.dynamicPropertyNames():
                    if bytes(prop).decode().startswith('language'):check(widget.property(bytes(prop).decode()))
                if isinstance(widget,QComboBox):
                    for i in range(widget.count()):check(widget.itemData(i,SOURCE_ROLE))
                if isinstance(widget,QListWidget):
                    for i in range(widget.count()):check(widget.item(i).data(SOURCE_ROLE))
                if isinstance(widget,QTableWidget):
                    for i in range(widget.columnCount()):
                        item=widget.horizontalHeaderItem(i)
                        if item:check(item.data(SOURCE_ROLE))
        inventory(window)
        window.grab().save(str(output/f'English_Settings_{scale}.png'))
        window.toast.notify(translate('Einstellungen'),translate('Änderungen gespeichert und angewendet.'))
        app.processEvents();inventory(window);window.grab().save(str(output/f'English_Toast_{scale}.png'));window.toast.dismiss()
        window.resize(820,600);app.processEvents();window.grab().save(str(output/f'English_Compact_{scale}.png'))
        data={'entity':'companies','record':None,'choices':{'companies':[],'jobs':[],'applicants':[]},'statuses':[]}
        dialog=RecordDialog(data,window);dialog.fields['name'].setText('Vorlagen');dialog.show();app.processEvents();inventory(dialog)
        dialog.grab().save(str(output/f'English_Record_{scale}.png'));dialog.reject()
        wizard=ProjectWizard(window);wizard.fields['name'].setText('Vorlagen');wizard.fields['goal'].setPlainText('Speichern {{NAME}}')
        wizard.refresh_summary(2);wizard.show();app.processEvents();inventory(wizard)
        wizard.grab().save(str(output/f'English_Project_{scale}.png'));wizard.reject()
        wizard.setStartId(2);wizard.restart();wizard.show();app.processEvents()
        wizard.grab().save(str(output/f'English_Project_Summary_{scale}.png'));wizard.reject()
        wizard_summary_english=wizard.summary.toPlainText()
        # Switch back after an English startup, including every settings choice.
        window.apply_preferences(Preferences(language='de',reduced_motion=True));app.processEvents()
        german=window.pages['settings'].tabs.tabText(1)
        theme_german=window.pages['settings'].theme.itemText(0)
        window.grab().save(str(output/f'German_Compact_{scale}.png'))
        result={'scale_requested':scale,'device_pixel_ratio':window.devicePixelRatioF(),'logical_size':[window.width(),window.height()],
                'owned_caption_sources':len(sources),'missing_catalog_sources':sorted(missing),
                'german_tab_after_english_start':german,'german_theme_after_english_start':theme_german,
                'user_value':'Vorlagen','user_value_unchanged':dialog.fields['name'].text()=='Vorlagen',
                'wizard_summary_english':'Project goal: Speichern {{NAME}}' in wizard_summary_english,
                'wizard_user_value_unchanged':wizard.fields['name'].text()=='Vorlagen' and wizard.fields['goal'].toPlainText()=='Speichern {{NAME}}',
                'offscreen':True,'native_keyboard_or_dpi_acceptance':False,'gmail_attempts':0}
        result['ok']=not missing and german=='Arbeitsbereich / Listen' and theme_german=='Klar · Hell' and result['user_value_unchanged'] and result['wizard_summary_english'] and result['wizard_user_value_unchanged']
        window.close();deadline=time.monotonic()+10
        while window.controller.thread.isRunning() and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
        if window.controller.thread.isRunning():raise RuntimeError('Shutdown did not finish')
        window.deleteLater();app.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
    (output/f'Render_{scale}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--scale',default='100');args=parser.parse_args()
    result=capture(args.scale,ROOT/'docs/abnahme/A5_Localization')
    sys.exit(0 if result['ok'] else 1)
