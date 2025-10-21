import os, sys, subprocess, threading, queue, json, shutil, time, tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog, colorchooser
import tkinter.font as tkfont

# ========= Theme =========
BG_COLOR   = "#1e1e1e"
PANEL_BG   = "#232323"
EDITOR_BG  = "#272822"
EDITOR_FG  = "#f8f8f2"
FG_COLOR   = "#e0e0e0"
ACCENT     = "#ff9900"
ACCENT_2   = "#66d9ef"
ACCENT_3   = "#a6e22e"
ACCENT_4   = "#ffd866"

BTN_BG     = "#2a2a2a"
BTN_FG     = "#f0f0f0"
BTN_ACTIVE = "#3a3a3a"

DEFAULT_EXTS = [
    '.py','.pyw','.ipynb','.js','.ts','.html','.css','.json',
    '.md','.txt','.java','.c','.cpp','.h','.cs','.go','.rb',
    '.php','.sh','.bat','.ps1','.rs','.swift','.kt','.lua',
    '.sql','.yaml','.yml','.xml','.ini','.cfg','.toml'
]

SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".runpad_pro_settings.json")

# ======== Seguridad ejecución ========
ALLOWED_EXTS = (".py", ".pyw")
def _is_allowed_script(path: str) -> bool:
    try:
        return os.path.splitext(path)[1].lower() in ALLOWED_EXTS and os.path.isfile(path)
    except Exception:
        return False

# ========= Settings =========
def load_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "last_dir": os.getcwd(),
            "wrap": True,
            "font_size": 13,
            "symbol_color": ACCENT_2,
            "number_color": ACCENT_3,
            "alpha_color": ACCENT_4,
            # nuevos
            "persist_automator": True,
            "automator_items": [],
            "automator_marked": [],
        }

def save_settings(s):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass

# ========= App =========
class RunPad:
    def __init__(self, root):
        self.root = root
        self.root.title("RunPad Pro+ v1.0")
        self.root.geometry("1400x900")
        self.root.configure(bg=BG_COLOR)

        self.settings = load_settings()
        self.current_directory = self.settings.get("last_dir", os.getcwd())
        self.wrap = tk.BooleanVar(value=self.settings.get("wrap", True))
        self.font_size = tk.IntVar(value=int(self.settings.get("font_size", 13)))
        self.symbol_color = tk.StringVar(value=self.settings.get("symbol_color", ACCENT_2))
        self.number_color = tk.StringVar(value=self.settings.get("number_color", ACCENT_3))
        self.alpha_color  = tk.StringVar(value=self.settings.get("alpha_color", ACCENT_4))

        self.current_file = None
        self.file_modified = False

        self.scripts_list = []
        self.scripts_marked = set()
        # restaurar automatizador
        if self.settings.get("persist_automator", True):
            self.scripts_list = [p for p in self.settings.get("automator_items", []) if os.path.exists(p)]
            self.scripts_marked = set([p for p in self.settings.get("automator_marked", []) if os.path.exists(p)])

        self.proc_lock = threading.Lock()
        self.running_procs = []
        self.output_queue = queue.Queue()

        self._dragging = False
        self._init_styles()
        self._build_ui()
        self._bind_shortcuts()
        self.refresh_file_list()
        self._drain_output_queue()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ========= Styles =========
    def _init_styles(self):
        style = ttk.Style()
        try: style.theme_use("clam")
        except Exception: pass
        sb_common = dict(background=BTN_BG, troughcolor=BG_COLOR, bordercolor=BG_COLOR,
                         lightcolor=PANEL_BG, darkcolor=PANEL_BG, arrowcolor=FG_COLOR)
        style.configure("Dark.Vertical.TScrollbar", **sb_common)
        style.configure("Dark.Horizontal.TScrollbar", **sb_common)
        style.map("Dark.Vertical.TScrollbar", background=[("active", BTN_ACTIVE)])
        style.map("Dark.Horizontal.TScrollbar", background=[("active", BTN_ACTIVE)])
        style.configure("Dark.TCombobox", fieldbackground=BG_COLOR, background=PANEL_BG,
                        foreground=FG_COLOR, arrowcolor=FG_COLOR)
        style.map("Dark.TCombobox", fieldbackground=[('readonly', BG_COLOR)], foreground=[('readonly', FG_COLOR)])

    # ========= UI =========
    def _btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, bg=BTN_BG, fg=BTN_FG,
                         activebackground=BTN_ACTIVE, activeforeground=FG_COLOR,
                         relief="flat", padx=10, pady=6, bd=0, highlightthickness=0)

    def _btn_orange(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, bg=ACCENT, fg="#101010",
                         activebackground="#ffb347", activeforeground="#101010",
                         relief="flat", padx=12, pady=6, bd=0, highlightthickness=0)

    def _btn_sm(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, bg=BTN_BG, fg=BTN_FG,
                         activebackground=BTN_ACTIVE, activeforeground=FG_COLOR,
                         relief="flat", padx=6, pady=4, bd=0, highlightthickness=0,
                         font=("Consolas", 9))

    def _build_ui(self):
        # Menú
        menubar = tk.Menu(self.root, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Nuevo (Ctrl+N)", command=self.new_file)
        file_menu.add_command(label="Guardar (Ctrl+S)", command=lambda: self.save_file(show_popup=True))
        file_menu.add_command(label="Guardar como… (F12 / Ctrl+Shift+S)", command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Seleccionar carpeta (Ctrl+O)", command=self.select_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=self._on_close)
        menubar.add_cascade(label="Archivo", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Buscar (Ctrl+F)", command=self.open_find_dialog)
        edit_menu.add_command(label="Reemplazar (Ctrl+H)", command=self.open_replace_dialog)
        edit_menu.add_separator()
        edit_menu.add_command(label="Limpiar salida", command=self.clear_output)
        edit_menu.add_command(label="Copiar salida", command=self.copy_output)
        edit_menu.add_separator()
        edit_menu.add_command(label="Limpiar editor", command=self.clear_editor)
        menubar.add_cascade(label="Editar", menu=edit_menu)

        run_menu = tk.Menu(menubar, tearoff=0)
        run_menu.add_command(label="Ejecutar archivo actual (F5)", command=self.run_file)
        run_menu.add_command(label="Ejecutar scripts del automatizador", command=self.run_scripts_list)
        run_menu.add_command(label="Detener ejecución", command=self.stop_all)
        menubar.add_cascade(label="Ejecutar", menu=run_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Abrir terminal", command=self.open_terminal)
        menubar.add_cascade(label="Herramientas", menu=tools_menu)
        self.root.config(menu=menubar)

        # Toolbar
        toolbar = tk.Frame(self.root, bg=BG_COLOR); toolbar.pack(fill='x', padx=10, pady=6)
        self._btn(toolbar, "Nuevo", self.new_file).pack(side='left', padx=4)
        self._btn(toolbar, "Guardar", lambda: self.save_file(show_popup=True)).pack(side='left', padx=4)
        self._btn(toolbar, "Limpiar editor", self.clear_editor).pack(side='left', padx=4)
        self._btn(toolbar, "Ejecutar ▶", self.run_file).pack(side='left', padx=8)
        self._btn_orange(toolbar, "Python ▶", self.run_python_current).pack(side='left', padx=8)
        self._btn(toolbar, "Detener ⏹", self.stop_all).pack(side='left', padx=8)
        self._btn(toolbar, "Abrir Terminal", self.open_terminal).pack(side='left', padx=8)
        self._btn(toolbar, "Limpiar salida", self.clear_output).pack(side='left', padx=8)
        self._btn(toolbar, "Copiar salida", self.copy_output).pack(side='left', padx=8)

        # Split principal
        main = tk.PanedWindow(self.root, orient='horizontal', bg=BG_COLOR, sashrelief='flat', sashwidth=6)
        main.pack(fill='both', expand=True, padx=8, pady=8)

        # Izquierda: editor + consola
        left = tk.PanedWindow(main, orient='vertical', bg=BG_COLOR, sashrelief='flat', sashwidth=6)
        main.add(left, stretch="always")

        editor_frame = tk.LabelFrame(left, text="Editor", bg=PANEL_BG, fg=ACCENT)
        left.add(editor_frame, stretch="always")
        editor_container = tk.Frame(editor_frame, bg=PANEL_BG); editor_container.pack(fill='both', expand=True)

        self.linenos = tk.Text(editor_container, width=6, padx=6, takefocus=0, bg="#1b1b1b",
                               fg="#9e9e9e", state='disabled', relief="flat")
        self.linenos.pack(side='left', fill='y')

        self.editor = tk.Text(
            editor_container,
            wrap='word' if self.wrap.get() else 'none',
            font=("Consolas", self.font_size.get()),
            undo=True,
            bg=EDITOR_BG, fg=EDITOR_FG,
            insertbackground=ACCENT_2,
            relief="flat", bd=0,
            padx=10, pady=8,
            spacing1=2, spacing2=1, spacing3=2
        )
        self.editor.pack(side='left', fill='both', expand=True)

        # Tabs a 4 espacios
        self._set_editor_tabs(4)

        yscroll = ttk.Scrollbar(editor_container, orient='vertical',
                                command=self._on_scroll, style="Dark.Vertical.TScrollbar")
        yscroll.pack(side='right', fill='y')
        self.editor.config(yscrollcommand=lambda *a: (yscroll.set(*a), self._update_linenos()))
        self.linenos.config(yscrollcommand=yscroll.set)

        self.editor.bind('<<Modified>>', self._on_modified)
        self.editor.bind("<KeyRelease>", lambda e: (self._update_status_caret(), self._highlight_all()))
        self.editor.bind("<ButtonRelease-1>", lambda e: self._update_status_caret())
        self.editor.bind("<Tab>", self._soft_tab)

        out_frame = tk.LabelFrame(left, text="Consola", bg=PANEL_BG, fg=ACCENT)
        left.add(out_frame)
        out_container = tk.Frame(out_frame, bg=PANEL_BG); out_container.pack(fill='both', expand=True)
        self.output = tk.Text(out_container, height=14, wrap='word', font=("Consolas", 11),
                              bg=BG_COLOR, fg=FG_COLOR, insertbackground=FG_COLOR,
                              state='normal', relief="flat")
        self.output.pack(side='left', fill='both', expand=True)
        out_scroll = ttk.Scrollbar(out_container, orient='vertical',
                                   command=self.output.yview, style="Dark.Vertical.TScrollbar")
        out_scroll.pack(side='right', fill='y')
        self.output.config(yscrollcommand=out_scroll.set)

        # Derecha: contenedor desplazable (Canvas + Scrollbar)
        right_outer = tk.Frame(main, bg=PANEL_BG); main.add(right_outer, width=720)
        self.right_canvas = tk.Canvas(right_outer, bg=PANEL_BG, highlightthickness=0)
        right_scroll = ttk.Scrollbar(right_outer, orient='vertical',
                                     command=self.right_canvas.yview, style="Dark.Vertical.TScrollbar")
        self.right_canvas.configure(yscrollcommand=right_scroll.set)
        self.right_canvas.pack(side='left', fill='both', expand=True)
        right_scroll.pack(side='right', fill='y')

        right = tk.Frame(self.right_canvas, bg=PANEL_BG)
        self.right_canvas.create_window((0, 0), window=right, anchor='nw')

        def _update_scrollregion(_=None):
            self.right_canvas.configure(scrollregion=self.right_canvas.bbox("all"))
        right.bind("<Configure>", _update_scrollregion)

        # ----- Secciones dentro del panel derecho (todas desplazables) -----

        # Carpeta actual
        folder_view = tk.LabelFrame(right, text="Carpetas", bg=PANEL_BG, fg=ACCENT)
        folder_view.pack(fill='x', padx=6, pady=(6,6))

        top_row = tk.Frame(folder_view, bg=PANEL_BG); top_row.pack(fill='x', padx=6, pady=4)
        self.folder_label = tk.Label(top_row, text=self._folder_text(), bg=PANEL_BG, fg=ACCENT_2, anchor='w')
        self.folder_label.pack(side='left', padx=4)
        self._btn(top_row, "⬅ Atrás", self.go_parent).pack(side='right', padx=4)
        self._btn(top_row, "➕ Carpeta", self.make_new_folder).pack(side='right', padx=4)

        rename_row = tk.Frame(folder_view, bg=PANEL_BG); rename_row.pack(fill='x', padx=6, pady=4)
        tk.Label(rename_row, text="Nombre actual:", bg=PANEL_BG, fg=FG_COLOR).pack(side='left')
        self.curr_name_var = tk.StringVar(value=os.path.basename(self.current_directory) or self.current_directory)
        e = tk.Entry(rename_row, textvariable=self.curr_name_var, width=28,
                     bg=BG_COLOR, fg=FG_COLOR, insertbackground=FG_COLOR, relief="flat")
        e.pack(side='left', padx=8)
        e.bind("<Return>", lambda _e: self.rename_current_folder())
        self._btn(rename_row, "✎ Renombrar", self.rename_current_folder).pack(side='left', padx=4)

        path_row = tk.Frame(folder_view, bg=PANEL_BG); path_row.pack(fill='x', padx=6, pady=4)
        tk.Label(path_row, text="Ruta:", bg=PANEL_BG, fg=FG_COLOR).pack(side='left')
        self.path_var = tk.StringVar(value=self.current_directory)
        path_entry = tk.Entry(path_row, textvariable=self.path_var, width=58,
                              bg=BG_COLOR, fg=FG_COLOR, insertbackground=FG_COLOR, relief="flat")
        path_entry.pack(side='left', padx=8)
        self._btn(path_row, "📂 Seleccionar", self.select_folder).pack(side='left', padx=4)
        self._btn(path_row, "⟳ Refrescar", self.refresh_path).pack(side='left', padx=4)

        # Subcarpetas
        sub_frame = tk.LabelFrame(right, text="Subcarpetas", bg=PANEL_BG, fg=ACCENT)
        sub_frame.pack(fill='x', padx=6, pady=6)
        sub_container = tk.Frame(sub_frame, bg=PANEL_BG); sub_container.pack(fill='x')
        self.sub_list = tk.Listbox(sub_container, height=8, bg=BG_COLOR, fg=FG_COLOR,
                                   selectbackground=ACCENT, selectforeground="#0b0b0b",
                                   font=("Consolas",10), selectmode='browse', relief="flat", activestyle='dotbox')
        self.sub_list.pack(side='left', fill='x', expand=True, padx=(6,0), pady=6)
        sub_scroll = ttk.Scrollbar(sub_container, orient='vertical',
                                   command=self.sub_list.yview, style="Dark.Vertical.TScrollbar")
        sub_scroll.pack(side='right', fill='y', padx=(0,6), pady=6)
        self.sub_list.config(yscrollcommand=sub_scroll.set)
        self.sub_list.bind("<Double-Button-1>", lambda e: self.enter_selected_subfolder())
        self.sub_list.bind("<Button-3>", self._sub_list_menu)

        sub_btns = tk.Frame(sub_frame, bg=PANEL_BG); sub_btns.pack(fill='x', padx=6, pady=(0,6))
        self._btn(sub_btns, "Entrar", self.enter_selected_subfolder).pack(side='left', padx=4)
        self._btn(sub_btns, "Nueva", self.new_subfolder).pack(side='left', padx=4)
        self._btn(sub_btns, "Renombrar", self.rename_selected_subfolder).pack(side='left', padx=4)
        self._btn(sub_btns, "Eliminar", self.delete_selected_subfolder).pack(side='left', padx=4)

        # Archivos
        file_frame = tk.LabelFrame(right, text="Archivos (multi-selección y arrastre → Automatizador)", bg=PANEL_BG, fg=ACCENT)
        file_frame.pack(fill='both', expand=True, padx=6, pady=6)

        self.file_filter = tk.BooleanVar(value=True)
        tk.Checkbutton(file_frame, text="Solo extensiones conocidas",
                       variable=self.file_filter, command=self.refresh_file_list,
                       bg=PANEL_BG, fg=FG_COLOR, selectcolor=BG_COLOR, activebackground=PANEL_BG
                       ).pack(anchor='w', padx=8, pady=(6,0))

        file_container = tk.Frame(file_frame, bg=PANEL_BG); file_container.pack(fill='both', expand=True)
        self.file_list = tk.Listbox(file_container, bg=BG_COLOR, fg=FG_COLOR,
                                    selectbackground=ACCENT, selectforeground="#0b0b0b",
                                    font=("Consolas",10), selectmode='extended', relief="flat", activestyle='dotbox')
        self.file_list.pack(side='left', fill='both', expand=True, padx=(6,0), pady=6)
        file_scroll = ttk.Scrollbar(file_container, orient='vertical',
                                    command=self.file_list.yview, style="Dark.Vertical.TScrollbar")
        file_scroll.pack(side='right', fill='y', padx=(0,6), pady=6)
        self.file_list.config(yscrollcommand=file_scroll.set)
        self.file_list.bind("<Double-Button-1>", self._open_selected_file)
        self.file_list.bind("<Button-3>", self._file_list_menu)
        self.file_list.bind("<ButtonPress-1>", self._on_file_press)
        self.file_list.bind("<B1-Motion>", self._on_file_drag)
        self.file_list.bind("<ButtonRelease-1>", self._on_file_release)

        # --- Automatizador ---
        auto_frame = tk.LabelFrame(right, text="Automatizador", bg=PANEL_BG, fg=ACCENT)
        auto_frame.pack(fill='both', expand=True, padx=6, pady=6)

        row1 = tk.Frame(auto_frame, bg=PANEL_BG); row1.pack(fill='x', padx=6, pady=(6,2))
        self._btn_sm(row1, "Agregar script…", self.add_script).pack(side='left', padx=3)
        self._btn_sm(row1, "Agregar selección →", self.add_selected_files).pack(side='left', padx=3)

        row2 = tk.Frame(auto_frame, bg=PANEL_BG); row2.pack(fill='x', padx=6, pady=(0,6))
        self._btn_sm(row2, "Marcar todo", self.mark_all).pack(side='left', padx=3)
        self._btn_sm(row2, "Desmarcar todo", self.unmark_all).pack(side='left', padx=3)
        self._btn_sm(row2, "Limpiar lista", self.clear_list).pack(side='left', padx=3)

        list_container = tk.Frame(auto_frame, bg=PANEL_BG); list_container.pack(fill='both', expand=True, padx=6, pady=(0,6))
        self.script_box = tk.Listbox(
            list_container, bg=BG_COLOR, fg=FG_COLOR,
            selectbackground=ACCENT, selectforeground="#0b0b0b",
            height=16, relief="flat", activestyle='dotbox'
        )
        self.script_box.pack(side='left', fill='both', expand=True)
        sb = ttk.Scrollbar(list_container, orient='vertical', command=self.script_box.yview, style="Dark.Vertical.TScrollbar")
        sb.pack(side='right', fill='y')
        self.script_box.config(yscrollcommand=sb.set)
        self.script_box.bind("<Double-Button-1>", self.toggle_mark_selected)
        self.script_box.bind("<Button-3>", self._script_box_menu)

        # Botón inferior
        self._btn_sm(auto_frame, "Ejecutar scripts ▶", self.run_scripts_list).pack(fill='x', padx=6, pady=(0,6))

        # Status
        self.status = tk.Label(self.root, text="Listo", anchor='w', bg=BG_COLOR, fg=ACCENT_2)
        self.status.pack(fill='x', side='bottom')

        self._build_context_menu()
        self._toggle_wrap()
        self._apply_highlight_tags()
        self._highlight_all()
        self._refresh_subfolders()

    def _bind_shortcuts(self):
        self.root.bind_all("<Control-s>", lambda e: self.save_file(show_popup=True))
        self.root.bind_all("<Control-S>", lambda e: self.save_as())
        self.root.bind_all("<Control-n>", lambda e: self.new_file())
        self.root.bind_all("<Control-o>", lambda e: self.select_folder())
        self.root.bind_all("<F12>", lambda e: self.save_as())
        self.root.bind_all("<F5>", lambda e: self.run_file())
        self.root.bind_all("<Control-Key-plus>", lambda e: self._zoom(1))
        self.root.bind_all("<Control-KP_Add>", lambda e: self._zoom(1))
        self.root.bind_all("<Control-Key-minus>", lambda e: self._zoom(-1))
        self.root.bind_all("<Control-KP_Subtract>", lambda e: self._zoom(-1))
        self.root.bind_all("<Control-Key-0>", lambda e: self._zoom(reset=True))
        self.root.bind_all("<Control-f>", lambda e: self.open_find_dialog())
        self.root.bind_all("<Control-h>", lambda e: self.open_replace_dialog())
        self.root.bind_all("<Control-l>", lambda e: self.clear_output())

    # ========= Editor =========
    def _set_editor_tabs(self, spaces=4):
        fnt = tkfont.Font(font=self.editor["font"])
        tab_w = fnt.measure(" " * spaces)
        self.editor.config(tabs=(tab_w,))

    def _soft_tab(self, event):
        self.editor.insert(tk.INSERT, " " * 4)
        return "break"

    def clear_editor(self):
        self.editor.delete('1.0', 'end')
        self.file_modified = True
        self._update_linenos(force=True)
        self._highlight_all()
        self._set_status("Editor limpio")

    def new_file(self):
        if not self._maybe_discard_changes(mode="prompt"): return
        self.editor.delete('1.0','end')
        self.current_file = None
        self.file_modified = False
        if not hasattr(self, "filename_var"): self.filename_var = tk.StringVar(value="")
        if not hasattr(self, "ext_var"): self.ext_var = tk.StringVar(value=".py")
        self.filename_var.set(""); self.ext_var.set(".py")
        self._update_linenos(force=True)
        self._highlight_all()
        self._set_status("Nuevo archivo")

    def save_file(self, show_popup=True):
        if not self.current_file:
            if not hasattr(self, "filename_var"): self.filename_var = tk.StringVar(value="script")
            if not hasattr(self, "ext_var"): self.ext_var = tk.StringVar(value=".py")
            name = self.filename_var.get().strip() or "script"
            ext = self.ext_var.get().strip() or ".py"
            self.current_file = os.path.join(self.current_directory, name+ext)
        else:
            base = self.filename_var.get().strip() or os.path.splitext(os.path.basename(self.current_file))[0]
            ext = self.ext_var.get().strip() or os.path.splitext(self.current_file)[1]
            new_path = os.path.join(self.current_directory, base+ext)
            if new_path != self.current_file: self.current_file = new_path
        try:
            with open(self.current_file, 'w', encoding='utf-8') as f:
                f.write(self.editor.get('1.0', 'end-1c'))
            self.file_modified = False
            self._set_status(f"Guardado: {os.path.basename(self.current_file)}")
            if show_popup:
                messagebox.showinfo("Guardado", f"Archivo guardado:\n{self.current_file}")
            self.refresh_file_list()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}")

    def save_as(self):
        name = getattr(self, "filename_var", tk.StringVar(value="script")).get().strip() or "script"
        ext = getattr(self, "ext_var", tk.StringVar(value=".py")).get().strip() or ".py"
        p = filedialog.asksaveasfilename(initialdir=self.current_directory, initialfile=name+ext)
        if p:
            self.current_file = p
            self.filename_var.set(os.path.splitext(os.path.basename(p))[0])
            self.ext_var.set(os.path.splitext(p)[1] or ".py")
            self.save_file(show_popup=True)

    def _on_modified(self, _e=None):
        if self.editor.edit_modified():
            self.file_modified = True
            self.editor.edit_modified(False)
            self._update_linenos()

    def _update_linenos(self, force=False):
        if not force and getattr(self, "_ln_last", None) == self.editor.index("end-1c"):
            self._sync_linenos(); return
        self._ln_last = self.editor.index("end-1c")
        self.linenos.config(state='normal'); self.linenos.delete('1.0','end')
        last_line = int(self.editor.index('end-1c').split('.')[0])
        self.linenos.insert('1.0', "\n".join(str(i) for i in range(1, last_line+1)))
        self._sync_linenos(); self.linenos.config(state='disabled')

    def _sync_linenos(self):
        first, _ = self.editor.yview()
        self.linenos.yview_moveto(first)

    def _on_scroll(self, *args):
        self.editor.yview(*args); self.linenos.yview(*args)

    def _toggle_wrap(self):
        self.editor.config(wrap='word' if self.wrap.get() else 'none')

    def _zoom(self, delta=0, reset=False):
        size = 12 if reset else max(8, min(40, self.font_size.get() + delta))
        self.font_size.set(size)
        self.editor.config(font=("Consolas", size))
        self._set_editor_tabs(4)

    # ---- Highlighting ----
    def _apply_highlight_tags(self):
        self.editor.tag_configure("sym", foreground=self.symbol_color.get())
        self.editor.tag_configure("num", foreground=self.number_color.get())
        self.editor.tag_configure("alpha", foreground=self.alpha_color.get())

    def choose_symbol_color(self):
        c = colorchooser.askcolor(color=self.symbol_color.get(), title="Color para símbolos")
        if c and c[1]:
            self.symbol_color.set(c[1]); self.settings["symbol_color"] = self.symbol_color.get()
            save_settings(self.settings); self._apply_highlight_tags(); self._highlight_all()

    def choose_number_color(self):
        c = colorchooser.askcolor(color=self.number_color.get(), title="Color para números")
        if c and c[1]:
            self.number_color.set(c[1]); self.settings["number_color"] = self.number_color.get()
            save_settings(self.settings); self._apply_highlight_tags(); self._highlight_all()

    def choose_alpha_color(self):
        c = colorchooser.askcolor(color=self.alpha_color.get(), title="Color para letras")
        if c and c[1]:
            self.alpha_color.set(c[1]); self.settings["alpha_color"] = self.alpha_color.get()
            save_settings(self.settings); self._apply_highlight_tags(); self._highlight_all()

    def _highlight_all(self):
        pat_sym   = r'[:,\+\-\%\"\!\#\$\&/\\\?\=\(\)\[\]\{\}\<\>\|\@\^\~\*\;\.]'
        pat_num   = r'\d'
        pat_alpha = r'[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]'
        for t in ("sym","num","alpha"):
            self.editor.tag_remove(t,"1.0","end")
        idx = "1.0"
        while True:
            pos = self.editor.search(pat_sym, idx, stopindex="end", regexp=True)
            if not pos: break
            end = f"{pos}+1c"; self.editor.tag_add("sym", pos, end); idx = end
        idx = "1.0"
        while True:
            pos = self.editor.search(pat_num, idx, stopindex="end", regexp=True)
            if not pos: break
            end = f"{pos}+1c"; self.editor.tag_add("num", pos, end); idx = end
        idx = "1.0"
        while True:
            pos = self.editor.search(pat_alpha, idx, stopindex="end", regexp=True)
            if not pos: break
            end = f"{pos}+1c"; self.editor.tag_add("alpha", pos, end); idx = end
        self.editor.tag_raise("sym"); self.editor.tag_lower("alpha"); self.editor.tag_lower("num")

    # ========= Folder Viewer helpers =========
    def _folder_text(self):
        try:
            files = os.listdir(self.current_directory)
            n = len([f for f in files if os.path.isfile(os.path.join(self.current_directory, f))])
        except Exception:
            n = 0
        base = os.path.basename(self.current_directory) or self.current_directory
        return f"📂 {base} ({n} archivos)"

    def _refresh_subfolders(self):
        self.sub_list.delete(0, 'end')
        try:
            subs = [d for d in sorted(os.listdir(self.current_directory))
                    if os.path.isdir(os.path.join(self.current_directory, d))]
            for s in subs: self.sub_list.insert('end', s)
        except Exception as e:
            self._set_status(f"Error listando subcarpetas: {e}")

    def _selected_subfolder(self):
        sel = self.sub_list.curselection()
        return self.sub_list.get(sel[0]) if sel else None

    def enter_selected_subfolder(self):
        name = self._selected_subfolder()
        if not name: return
        target = os.path.join(self.current_directory, name)
        if os.path.isdir(target):
            if not self._maybe_discard_changes(mode="nav"): return
            self.current_directory = target
            self.settings["last_dir"] = target; save_settings(self.settings)
            self.refresh_file_list(); self._refresh_folder_widgets(); self._refresh_subfolders()

    def new_subfolder(self):
        name = simpledialog.askstring("Nueva subcarpeta", "Nombre:", parent=self.root)
        if not name: return
        path = os.path.join(self.current_directory, name)
        try:
            os.makedirs(path, exist_ok=False); self._refresh_subfolders()
        except FileExistsError:
            messagebox.showerror("Error", "Ya existe una carpeta con ese nombre.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo crear:\n{e}")

    def rename_selected_subfolder(self):
        name = self._selected_subfolder()
        if not name:
            messagebox.showinfo("Info", "Selecciona una subcarpeta."); return
        old = os.path.join(self.current_directory, name)
        new_name = simpledialog.askstring("Renombrar subcarpeta", "Nuevo nombre:",
                                          initialvalue=name, parent=self.root)
        if not new_name: return
        new = os.path.join(self.current_directory, new_name)
        if os.path.exists(new):
            messagebox.showerror("Error", "Ya existe una carpeta con ese nombre."); return

        self.stop_all()
        old_cwd = os.getcwd()
        try:
            os.chdir(self.current_directory)
            for _ in range(4):
                try:
                    os.rename(old, new)
                    break
                except (PermissionError, OSError):
                    time.sleep(0.25)
            else:
                raise PermissionError("El sistema mantiene la carpeta en uso.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo renombrar:\n{e}\n\nCierra procesos o ventanas que usen esa carpeta.")
            return
        finally:
            try: os.chdir(old_cwd)
            except Exception: pass

        if self.current_file and self.current_file.startswith(old + os.sep):
            rel = os.path.relpath(self.current_file, old)
            self.current_file = os.path.join(new, rel)
        self._remap_scripts_paths(old, new)

        self._refresh_subfolders(); self.refresh_file_list()
        self._set_status(f"Subcarpeta renombrada a: {new_name}")

    def delete_selected_subfolder(self):
        name = self._selected_subfolder()
        if not name:
            messagebox.showinfo("Info", "Selecciona una subcarpeta."); return
        path = os.path.join(self.current_directory, name)
        if not os.path.isdir(path):
            self._refresh_subfolders(); return
        if not messagebox.askyesno("Eliminar", f"¿Eliminar subcarpeta '{name}'?"): return
        try:
            os.rmdir(path)
        except OSError:
            if messagebox.askyesno("Eliminar", "La carpeta no está vacía. ¿Eliminar recursivamente?"):
                try: shutil.rmtree(path)
                except Exception as e:
                    messagebox.showerror("Error", f"No se pudo eliminar:\n{e}"); return
            else:
                return
        self._refresh_subfolders(); self.refresh_file_list()

    def _refresh_folder_widgets(self):
        self.folder_label.config(text=self._folder_text())
        self.curr_name_var.set(os.path.basename(self.current_directory) or self.current_directory)
        self.path_var.set(self.current_directory)

    def go_parent(self):
        parent = os.path.dirname(self.current_directory)
        if parent and os.path.isdir(parent):
            if not self._maybe_discard_changes(mode="nav"): return
            self.current_directory = parent
            self.settings["last_dir"] = parent; save_settings(self.settings)
            self.refresh_file_list(); self._refresh_folder_widgets(); self._refresh_subfolders()

    def make_new_folder(self):
        name = simpledialog.askstring("Nueva carpeta", "Nombre de la carpeta:", parent=self.root)
        if not name: return
        new = os.path.join(self.current_directory, name)
        try:
            os.makedirs(new, exist_ok=True)
            if not self._maybe_discard_changes(mode="nav"): return
            self.current_directory = new
            self.settings["last_dir"] = new; save_settings(self.settings)
            self.refresh_file_list(); self._refresh_folder_widgets(); self._refresh_subfolders()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo crear carpeta:\n{e}")

    def rename_current_folder(self):
        new_name = self.curr_name_var.get().strip()
        if not new_name:
            messagebox.showerror("Error", "El nombre no puede estar vacío."); return
        parent = os.path.dirname(self.current_directory)
        old_path = self.current_directory
        new_path = os.path.join(parent, new_name)
        if new_path == old_path: return
        if os.path.exists(new_path):
            messagebox.showerror("Error", "Ya existe una carpeta con ese nombre."); return

        self.stop_all()
        old_cwd = os.getcwd()
        try:
            os.chdir(parent)
            for _ in range(4):
                try:
                    os.rename(old_path, new_path)
                    break
                except (PermissionError, OSError):
                    time.sleep(0.25)
            else:
                raise PermissionError("El sistema mantiene la carpeta en uso.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo renombrar:\n{e}\n\nCierra ventanas del Explorador o terminales que usen esta carpeta.")
            return
        finally:
            try: os.chdir(old_cwd)
            except Exception: pass

        if self.current_file and self.current_file.startswith(old_path + os.sep):
            rel = os.path.relpath(self.current_file, old_path)
            self.current_file = os.path.join(new_path, rel)
        self._remap_scripts_paths(old_path, new_path)

        self.current_directory = new_path
        self.settings["last_dir"] = new_path; save_settings(self.settings)
        self._refresh_folder_widgets(); self.refresh_file_list(); self._refresh_subfolders()
        self._set_status(f"Carpeta renombrada a: {new_name}")

    def _remap_scripts_paths(self, old_root, new_root):
        new_list = []
        new_marked = set()
        for p in self.scripts_list:
            if p.startswith(old_root + os.sep):
                rel = os.path.relpath(p, old_root)
                np = os.path.join(new_root, rel)
            else:
                np = p
            new_list.append(np)
            if p in self.scripts_marked:
                new_marked.add(np)
        self.scripts_list = new_list
        self.scripts_marked = new_marked
        self._refresh_script_box()
        self._persist_automator()

    # ========= Files =========
    def select_folder(self):
        d = filedialog.askdirectory(initialdir=self.current_directory)
        if d:
            if not self._maybe_discard_changes(mode="nav"): return
            self.current_directory = d
            self.settings["last_dir"] = d; save_settings(self.settings)
            self.refresh_file_list(); self._refresh_folder_widgets(); self._refresh_subfolders()

    def refresh_path(self):
        d = self.path_var.get().strip()
        if os.path.isdir(d):
            if not self._maybe_discard_changes(mode="nav"): return
            self.current_directory = d
            self.settings["last_dir"] = d; save_settings(self.settings)
            self.refresh_file_list(); self._set_status(f"Directorio cambiado: {d}")
            self._refresh_folder_widgets(); self._refresh_subfolders()
        else:
            messagebox.showerror("Error", "Ruta inválida")

    def _open_selected_file(self, event=None):
        sel = self.file_list.curselection()
        if not sel: return
        fname = self.file_list.get(sel[0])
        path = os.path.join(self.current_directory, fname)
        if not self._maybe_discard_changes(mode="prompt"): return
        try:
            with open(path, 'r', encoding='utf-8') as f: txt = f.read()
            self.editor.delete('1.0','end'); self.editor.insert('1.0', txt)
            self.current_file = path; self.file_modified = False
            if not hasattr(self, "filename_var"): self.filename_var = tk.StringVar(value="")
            if not hasattr(self, "ext_var"): self.ext_var = tk.StringVar(value=".py")
            self.filename_var.set(os.path.splitext(fname)[0])
            self.ext_var.set(os.path.splitext(fname)[1] or ".py")
            self._set_status(f"Abriste {fname}")
            self._update_linenos(force=True); self._highlight_all()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def refresh_file_list(self):
        self.file_list.delete(0,'end')
        try:
            files = sorted(os.listdir(self.current_directory))
            for f in files:
                p = os.path.join(self.current_directory, f)
                if os.path.isfile(p):
                    if self.file_filter.get():
                        if os.path.splitext(f)[1] in DEFAULT_EXTS:
                            self.file_list.insert('end', f)
                    else:
                        self.file_list.insert('end', f)
        except Exception as e:
            self._set_status(f"Error al listar: {e}")
        if hasattr(self, "folder_label"):
            self.folder_label.config(text=self._folder_text())

    def _file_list_menu(self, event):
        idx = self.file_list.nearest(event.y)
        if idx < 0: return
        self.file_list.selection_clear(0, 'end'); self.file_list.selection_set(idx)
        fname = self.file_list.get(idx); path = os.path.join(self.current_directory, fname)
        menu = tk.Menu(self.root, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
        menu.add_command(label="Abrir", command=self._open_selected_file)
        menu.add_command(label="Agregar al Automatizador", command=lambda: self._add_paths_to_automator([path]))
        menu.add_command(label="Renombrar", command=lambda: self._rename_file(path))
        menu.add_command(label="Eliminar", command=lambda: self._delete_file(path))
        try: menu.tk_popup(event.x_root, event.y_root)
        finally: menu.grab_release()

    def _sub_list_menu(self, event):
        idx = self.sub_list.nearest(event.y)
        if idx < 0: return
        self.sub_list.selection_clear(0, 'end'); self.sub_list.selection_set(idx)
        menu = tk.Menu(self.root, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
        menu.add_command(label="Entrar", command=self.enter_selected_subfolder)
        menu.add_command(label="Renombrar", command=self.rename_selected_subfolder)
        menu.add_command(label="Eliminar", command=self.delete_selected_subfolder)
        try: menu.tk_popup(event.x_root, event.y_root)
        finally: menu.grab_release()

    def _rename_file(self, path):
        base = os.path.basename(path)
        new = filedialog.asksaveasfilename(initialdir=self.current_directory, initialfile=base)
        if new and new != path:
            try:
                os.replace(path, new); self.refresh_file_list()
                self._set_status(f"Renombrado a {os.path.basename(new)}")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo renombrar:\n{e}")

    def _delete_file(self, path):
        if messagebox.askyesno("Eliminar", f"¿Eliminar {os.path.basename(path)}?"):
            try:
                os.remove(path); self.refresh_file_list()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo eliminar:\n{e}")

    # Drag file list → automatizador
    def _on_file_press(self, event):
        self._dragging = False
        self._press_xy = (event.x_root, event.y_root)

    def _on_file_drag(self, event):
        if not hasattr(self, "_press_xy"): return
        dx = abs(event.x_root - self._press_xy[0]); dy = abs(event.y_root - self._press_xy[1])
        if dx + dy > 8: self._dragging = True

    def _on_file_release(self, event):
        if not self._dragging: return
        bx, by = self.script_box.winfo_rootx(), self.script_box.winfo_rooty()
        bw, bh = self.script_box.winfo_width(), self.script_box.winfo_height()
        if bx <= event.x_root <= bx + bw and by <= event.y_root <= by + bh:
            sel = self.file_list.curselection()
            if not sel: return
            paths = [os.path.join(self.current_directory, self.file_list.get(i)) for i in sel]
            self._add_paths_to_automator(paths)
            self._set_status(f"Agregados {len(paths)} elemento(s) por arrastre")
        self._dragging = False

    def add_selected_files(self):
        sel = self.file_list.curselection()
        if not sel: return
        paths = [os.path.join(self.current_directory, self.file_list.get(i)) for i in sel]
        self._add_paths_to_automator(paths)

    def _add_paths_to_automator(self, paths):
        added = 0
        for p in paths:
            if p and os.path.isfile(p) and p not in self.scripts_list:
                self.scripts_list.append(p); added += 1
        if added:
            self._refresh_script_box()
            self._persist_automator()
        self._set_status(f"Añadidos al automatizador: {added}")

    # ========= Automator =========
    def _refresh_script_box(self):
        self.script_box.delete(0, 'end')
        for p in self.scripts_list:
            mark = "[x]" if p in self.scripts_marked else "[ ]"
            self.script_box.insert('end', f"{mark} {os.path.basename(p)}")

    def toggle_mark_selected(self, event=None):
        sel = self.script_box.curselection()
        if not sel: return
        idx = sel[0]; p = self.scripts_list[idx]
        if p in self.scripts_marked: self.scripts_marked.remove(p)
        else: self.scripts_marked.add(p)
        self._refresh_script_box()
        self._persist_automator()

    def _script_box_menu(self, event):
        idx = self.script_box.nearest(event.y)
        if idx < 0: return
        self.script_box.selection_clear(0, 'end'); self.script_box.selection_set(idx)
        menu = tk.Menu(self.root, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
        menu.add_command(label="Marcar/Desmarcar", command=self.toggle_mark_selected)
        menu.add_command(label="Quitar de la lista", command=lambda: self._remove_script(idx))
        try: menu.tk_popup(event.x_root, event.y_root)
        finally: menu.grab_release()

    def _remove_script(self, idx):
        if 0 <= idx < len(self.scripts_list):
            p = self.scripts_list.pop(idx)
            if p in self.scripts_marked: self.scripts_marked.remove(p)
            self._refresh_script_box()
            self._persist_automator()

    def add_script(self):
        files = filedialog.askopenfilenames(initialdir=self.current_directory, title="Selecciona scripts")
        if files: self._add_paths_to_automator(files)

    def mark_all(self):
        self.scripts_marked = set(self.scripts_list)
        self._refresh_script_box()
        self._persist_automator()

    def unmark_all(self):
        self.scripts_marked = set()
        self._refresh_script_box()
        self._persist_automator()

    def clear_list(self):
        self.scripts_list.clear()
        self.scripts_marked.clear()
        self._refresh_script_box()
        self._persist_automator()

    # ========= Run =========
    def run_file(self):
        self.save_file(show_popup=False)
        if not self.current_file: return
        abs_path = os.path.abspath(self.current_file)
        ext = os.path.splitext(abs_path)[1].lower()
        if ext not in ALLOWED_EXTS:
            self.output_queue.put(f"\n[Saltado] Solo se ejecutan {ALLOWED_EXTS}. Archivo: {abs_path}\n")
            return
        folder = os.path.dirname(abs_path)
        cmd_list = [sys.executable, os.path.basename(abs_path)]
        threading.Thread(target=self._run_and_stream, args=(cmd_list, folder, False, abs_path),
                         daemon=True).start()

    def run_python_current(self):
        self.save_file(show_popup=False)
        if not self.current_file:
            messagebox.showinfo("Python ▶", "No hay archivo activo."); return
        ext = os.path.splitext(self.current_file)[1].lower()
        if ext not in (".py", ".pyw"):
            messagebox.showinfo("Python ▶", "El archivo activo no es .py/.pyw."); return
        self.run_file()

    def run_scripts_list(self):
        candidates = list(self.scripts_marked) if self.scripts_marked else list(self.scripts_list)
        existing = [p for p in candidates if os.path.exists(p) and _is_allowed_script(p)]
        missing = [p for p in candidates if not os.path.exists(p)]
        invalid = [p for p in candidates if os.path.exists(p) and not _is_allowed_script(p)]
        if missing:
            self.output_queue.put("\n[No existen:\n  - " + "\n  - ".join(missing) + "]\n")
        if invalid:
            self.output_queue.put("\n[No ejecutables (permitidos: .py, .pyw):\n  - " + "\n  - ".join(invalid) + "]\n")
        if not existing:
            self.output_queue.put("\n[No hay scripts válidos para ejecutar]\n"); return
        with self.proc_lock:
            self._batch_results = []; self._pending = len(existing)
        self.output_queue.put(f"\n=== Ejecutando {len(existing)} script(s) ===\n")
        for item in existing:
            folder = os.path.dirname(item)
            cmd_list = [sys.executable, os.path.basename(item)]
            threading.Thread(target=self._run_and_stream, args=(cmd_list, folder, False, item),
                             daemon=True).start()

    def stop_all(self):
        with self.proc_lock:
            for p in self.running_procs:
                try:
                    if os.name == "nt":
                        subprocess.Popen(f"taskkill /F /T /PID {p.pid}", shell=True)
                    else:
                        p.terminate()
                except Exception:
                    pass
            self.running_procs.clear()
        self.output_queue.put("\n[Procesos detenidos]\n")

    def _run_and_stream(self, cmd, cwd, use_shell, label=None):
        code = None
        try:
            head = cmd if isinstance(cmd, str) else " ".join(cmd)
            self.output_queue.put(f"\n> Ejecutando en: {cwd}\n> Comando: {head}\n")
            p = subprocess.Popen(cmd, cwd=cwd, shell=use_shell,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            with self.proc_lock: self.running_procs.append(p)
            for line in p.stdout: self.output_queue.put(line)
            p.wait(); code = p.returncode
            tag = os.path.basename(label) if label else head
            status = "OK" if code == 0 else f"FALLÓ ({code})"
            self.output_queue.put(f"\n[{status}] {tag}\n")
        except Exception as e:
            code = -1; self.output_queue.put(f"\n[Error: {e}]\n")
        finally:
            with self.proc_lock:
                try: self.running_procs.remove(p)
                except Exception: pass
                if label is not None and hasattr(self, "_pending"):
                    self._batch_results.append((label, code)); self._pending -= 1
                    if self._pending == 0:
                        ok = [os.path.basename(l) for l,c in self._batch_results if c == 0]
                        fail = [os.path.basename(l) for l,c in self._batch_results if c != 0]
                        summary = "\n== Resumen de ejecución ==\n"
                        summary += f"OK ({len(ok)}): " + (", ".join(ok) if ok else "ninguno") + "\n"
                        summary += f"FALLÓ ({len(fail)}): " + (", ".join(fail) if fail else "ninguno") + "\n"
                        self.output_queue.put(summary)

    # ========= Terminal =========
    def open_terminal(self):
        folder = self.current_directory
        try:
            if os.name == "nt":
                subprocess.Popen(f'start "" cmd /K "cd /d {folder}"', shell=True)
            elif sys.platform == "darwin":
                applescript = f'tell application "Terminal" to do script "cd \\"{folder}\\""'
                subprocess.Popen(['osascript', '-e', applescript])
            else:
                for term in ["x-terminal-emulator","gnome-terminal","konsole","xfce4-terminal","xterm"]:
                    try:
                        subprocess.Popen([term], cwd=folder); break
                    except Exception:
                        continue
                else:
                    messagebox.showinfo("Terminal", "Abre tu terminal y navega a:\n"+folder)
        except Exception as e:
            messagebox.showerror("Terminal", str(e))

    # ========= Consola =========
    def clear_output(self):
        self.output.config(state='normal'); self.output.delete('1.0','end'); self.output.config(state='normal')

    def copy_output(self):
        txt = self.output.get('1.0','end-1c')
        self.root.clipboard_clear(); self.root.clipboard_append(txt)
        self._set_status("Salida copiada")

    def _append_output(self, text):
        self.output.insert('end', text); self.output.see('end')

    def _drain_output_queue(self):
        try:
            while True:
                s = self.output_queue.get_nowait(); self._append_output(s)
        except queue.Empty:
            pass
        self.root.after(50, self._drain_output_queue)

    # ========= Buscar/Reemplazar =========
    def open_find_dialog(self): self._open_search_dialog(replace=False)
    def open_replace_dialog(self): self._open_search_dialog(replace=True)

    def _open_search_dialog(self, replace=False):
        win = tk.Toplevel(self.root); win.title("Buscar y reemplazar" if replace else "Buscar")
        win.resizable(False, False)
        tk.Label(win, text="Buscar:", bg=BG_COLOR, fg=FG_COLOR).grid(row=0, column=0, padx=6, pady=6, sticky='e')
        find_var = tk.StringVar()
        tk.Entry(win, textvariable=find_var, width=30, bg=PANEL_BG, fg=FG_COLOR,
                 insertbackground=FG_COLOR, relief="flat").grid(row=0, column=1, padx=6, pady=6)
        replace_var = tk.StringVar()
        if replace:
            tk.Label(win, text="Reemplazar con:", bg=BG_COLOR, fg=FG_COLOR).grid(row=1, column=0, padx=6, pady=6, sticky='e')
            tk.Entry(win, textvariable=replace_var, width=30, bg=PANEL_BG, fg=FG_COLOR,
                     insertbackground=FG_COLOR, relief="flat").grid(row=1, column=1, padx=6, pady=6)
        def do_find(): self._find_text(find_var.get())
        def do_replace(): self._replace_text(find_var.get(), replace_var.get())
        btn_row = 1 if not replace else 2
        tk.Button(win, text="Buscar siguiente", command=do_find, bg=BTN_BG, fg=BTN_FG,
                  activebackground=BTN_ACTIVE, relief="flat").grid(row=btn_row, column=0, padx=6, pady=6, sticky='we')
        if replace:
            tk.Button(win, text="Reemplazar todo", command=do_replace, bg=BTN_BG, fg=BTN_FG,
                      activebackground=BTN_ACTIVE, relief="flat").grid(row=btn_row, column=1, padx=6, pady=6, sticky='we')

    def _find_text(self, needle):
        if not needle: return
        start = self.editor.index(tk.INSERT)
        pos = self.editor.search(needle, start, stopindex='end')
        if not pos:
            pos = self.editor.search(needle, '1.0', stopindex=start)
            if not pos: self._set_status("No encontrado"); return
        end = f"{pos}+{len(needle)}c"
        self.editor.tag_remove('sel', '1.0', 'end')
        self.editor.tag_add('sel', pos, end)
        self.editor.mark_set(tk.INSERT, end); self.editor.see(pos)
        self._set_status(f"Encontrado en {pos}")

    def _replace_text(self, needle, repl):
        if not needle: return
        count = 0; idx = '1.0'
        while True:
            pos = self.editor.search(needle, idx, stopindex='end')
            if not pos: break
            end = f"{pos}+{len(needle)}c"
            self.editor.delete(pos, end); self.editor.insert(pos, repl)
            idx = f"{pos}+{len(repl)}c"; count += 1
        self._set_status(f"Reemplazados: {count}")

    # ========= Misc =========
    def _build_context_menu(self):
        self.ctx = tk.Menu(self.root, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
        self.ctx.add_command(label="Cortar", command=lambda: self.editor.event_generate("<<Cut>>"))
        self.ctx.add_command(label="Copiar", command=lambda: self.editor.event_generate("<<Copy>>"))
        self.ctx.add_command(label="Pegar", command=lambda: self.editor.event_generate("<<Paste>>"))
        self.editor.bind("<Button-3>", self._show_context)

    def _show_context(self, e):
        try: self.ctx.tk_popup(e.x_root, e.y_root)
        finally: self.ctx.grab_release()

    def _set_status(self, text):
        self.status.config(text=f"{text}   |  línea {self._cursor_line()} col {self._cursor_col()}")

    def _cursor_line(self): return self.editor.index(tk.INSERT).split('.')[0]
    def _cursor_col(self):  return self.editor.index(tk.INSERT).split('.')[1]
    def _update_status_caret(self): self._set_status("Listo")

    def _maybe_discard_changes(self, mode="prompt"):
        if not self.file_modified:
            return True
        if mode == "nav":
            if self.current_file:
                try:
                    with open(self.current_file, 'w', encoding='utf-8') as f:
                        f.write(self.editor.get('1.0', 'end-1c'))
                    self.file_modified = False
                    self._set_status(f"Guardado: {os.path.basename(self.current_file)}")
                except Exception:
                    pass
            return True
        r = messagebox.askyesnocancel("Cambios sin guardar", "¿Guardar cambios?")
        if r is None: return False
        if r: self.save_file(show_popup=False)
        return True

    def _on_close(self):
        self.settings["wrap"] = bool(self.wrap.get())
        self.settings["font_size"] = int(self.font_size.get())
        self.settings["symbol_color"] = self.symbol_color.get()
        self.settings["number_color"] = self.number_color.get()
        self.settings["alpha_color"]  = self.alpha_color.get()
        save_settings(self.settings)
        if not self._maybe_discard_changes(mode="prompt"): return
        try: self.stop_all()
        except Exception: pass
        self.root.destroy()

    # ========= Persistencia automatizador =========
    def _persist_automator(self):
        if not self.settings.get("persist_automator", True):
            return
        self.settings["automator_items"] = list(self.scripts_list)
        self.settings["automator_marked"] = list(self.scripts_marked)
        save_settings(self.settings)

# ========= Main =========
if __name__ == "__main__":
    root = tk.Tk()
    app = RunPad(root)
    root.mainloop()
