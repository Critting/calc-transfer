#!/usr/bin/env python

from tkinter import ttk
import tkinter as tk

class PokeIVWindow(tk.Frame):
    def __init__(self, config, data, session, master=None):
        super().__init__(master)
        self.data = data
        self.session = session
        self.logText = tk.StringVar()
        self.logText.set("idle...")
        self.transfer_ids = []
        self.evolve_ids = []
        self.check_boxes = {}
        self.config = config
        self.config_boxes = {}
        self.create_widgets()
        self.pack()
        
    def create_config_window(self):
        self.config_window = tk.Toplevel(self)
        self.config_window.wm_title("Config Window")
        
        for key in list(self.config.keys()):
            if (type(self.config[key]) != type(True)): #if not boolean
                if key == "evolve_list": #deprecated, don't show
                    continue
                self.config_boxes[key] = tk.StringVar()
                if isinstance(self.config[key], list):
                    self.config_boxes[key].set(",".join(map(str,self.config[key])))
                elif self.config[key] is not None:
                    self.config_boxes[key].set(self.config[key])
                else:
                    self.config_boxes[key].set("")
                frame = tk.Frame(self.config_window)
                label = tk.Label(frame, text=key, width=13, anchor="w", justify="left")
                label.pack(side="left")
                entry = tk.Entry(frame, width=50, textvariable=self.config_boxes[key])
                entry.pack(side="right", fill="both", expand=True)
                frame.pack(side="top", fill="both")
        
        save_button = tk.Button(self.config_window, text="Save", command=self.save_config_window)
        save_button.pack(side="bottom", fill="both")
        
    def save_config_window(self):
        self.set_config()
        self.config_window.destroy
        
    def show_config_window(self):
        self.create_config_window()
        return
        
    def hide_config_window(self):
        self.config_window.withdraw()
        return
        
    def reset_windows(self):
        self.list_windows.pack_forget()
        self.list_windows = self.create_list_windows(self.master_frame)
        self.list_windows.pack(side="left", fill="both")

    def create_widgets(self):
        self.master_frame = tk.Frame(self)        
        
        self.config_button = tk.Button(self.master_frame, text="Config", command=self.show_config_window)
        self.config_button.pack(side="top", fill="both")
        self.list_windows = self.create_list_windows(self.master_frame)
        self.list_windows.pack(side="top", fill="both")
        self.log = tk.Label(self.master_frame, textvariable=self.logText, bg="#D0F0C0", anchor="w", justify="left")
        self.log.pack(side="bottom", fill="both")
        self.init_windows = self.create_interactive(self.master_frame)
        self.init_windows.pack(side="bottom", fill="both")
        self.master_frame.pack(fill="both")
    
    def set_config(self):
        for key in list(self.config_boxes.keys()):
            if self.config_boxes[key].get() == 1:
                self.config[key] = True
            elif self.config_boxes[key].get() == 0:
                self.config[key] = False
            elif (key == "black_list" or key == "white_list") and self.config_boxes[key].get():
                self.config[key] = self.config_boxes[key].get().split(',')
            elif not self.config_boxes[key].get():
                self.config[key] = None
            elif type(self.config_boxes[key].get()) == str:
                self.config[key] = self.config_boxes[key].get()
        
        self.data.reconfigure(self.config)
        self.reset_windows()
    
    def create_checkbuttons(self, master):
        checkboxes = tk.Frame(master)
        
        for key in list(self.config.keys()):
            if (type(self.config[key]) == type(True)): #if boolean
                self.config_boxes[key] = tk.BooleanVar()
                if self.config[key]:
                    self.config_boxes[key].set(1)
                else:
                    self.config_boxes[key].set(0)
                self.check_boxes[key] = tk.Checkbutton(checkboxes, text=key, variable=self.config_boxes[key], command=self.set_config)
                self.check_boxes[key].pack(side="bottom", anchor="w")
                
        return checkboxes
    
    def create_interactive(self, master):
        right_windows = tk.Frame(master)
        
        button_frame = tk.Frame(master)
        action_buttons = tk.Frame(button_frame)
        self.evolve_button = tk.Button(action_buttons, text="Evolve", command=self.evolve_pokemon)
        self.evolve_button.pack(side="top", fill="both")
        self.transfer_button = tk.Button(action_buttons, text="Transfer", command=self.transfer_pokemon)
        self.transfer_button.pack(side="bottom", fill="both")
        action_buttons.pack(side="left", fill="both", expand=True)
        self.cancel_button = tk.Button(button_frame, text="Cancel", command=self.cancel_actions, width=4, bg="#CD5C5C")
        self.cancel_button.pack(side="right", fill="y")
        button_frame.pack(side="bottom", fill="both")
        
        
        self.tickboxes = self.create_checkbuttons(master)
        self.tickboxes.pack(side="bottom", fill="both")
        
        return right_windows
    
    def create_list_windows(self, master):
        list_windows = tk.Frame(master)
        top_windows = tk.Frame(list_windows)
        btm_windows = tk.Frame(list_windows)
        
        self.best_window = self.create_window('Highest IV Pokemon', self.data["best"], top_windows)
        self.best_window.pack(side="left", fill="both")
        self.other_window = self.create_window('Other Pokemon', self.data["other"], top_windows)
        self.other_window.pack(side="right", fill="both")
        self.transfer_window = self.create_window('Transfer candidates', self.data["transfer"], btm_windows)
        self.transfer_window.pack(side="left", fill="both")
        self.evolve_window = self.create_window('Evolution candidates', self.data["evolve"], btm_windows)
        self.evolve_window.pack(side="right", fill="both")
    
        top_windows.pack(side="top", fill="both")
        btm_windows.pack(side="bottom", fill="both")
        
        return list_windows
    
    def create_window(self, name, pokemon, master):
        frame = tk.Frame(master)
        title = tk.Label(frame, text=name)
        title.pack(side="top", fill="both")
        
        cols = columns=self.get_columns()
        tree = ttk.Treeview(frame, columns=cols["text"][1:])
        for i, x in enumerate(cols["text"]):
            tree.heading('#'+str(i), text=x)
            tree.column('#'+str(i), width=cols["width"][i], stretch="yes")
        for p in pokemon:
            info = self.get_info(p)
            tree.insert('', 'end', text=info[0], values=info[1:])
        tree.pack(side="left", fill="both")
        
        scroll = tk.Scrollbar(frame)
        scroll.pack(side="right", fill="both")
        
        scroll.config(command=tree.yview)
        tree.config(yscrollcommand=scroll.set)
        
        frame.tree = tree
        frame.scroll = scroll
        frame.title = title
        return frame
        
    def get_info(self,pokemon):
        if self.config["verbose"]:
            return self.get_info_verbose(pokemon)
        else:
            return self.get_info_min(pokemon)
    
    def get_info_min(self,pokemon):
        return (str(pokemon.name),str(pokemon.cp),str('{0:>2.2%}').format(pokemon.ivPercent))

    def get_info_verbose(self,pokemon):
        return (str(pokemon.name),str(pokemon.attack),str(pokemon.defense),str(pokemon.stamina),str(pokemon.cp),str('{0:>2.2%}').format(pokemon.ivPercent))
        
    def get_columns(self):
        if self.config["verbose"]:
            return {'text': ('POKEMON','ATK','DEF','STA','CP','IV'),
                    'width': (100,30,30,30,60,60)}
        else:
            return {'text': ('POKEMON','CP','IV'),
                    'width': (100,60,60)}   
                    
    def log_info(self, text, level=None):
        self.logText.set(text)
        if level == "working":
            self.log.configure(bg="yellow")
        elif level == "error":
            self.log.configure(bg="red")
        else:
            self.log.configure(bg="#D0F0C0")
    
    def evolve_pokemon(self):
        if self.data["evolve"]:
            p = self.data["evolve"][0]
            id = str(p.number)
            self.log_info('{0:<35} {1:<8} {2:<8.2%}'.format('evolving pokemon: '+str(p.name),str(p.cp),p.ivPercent), "working")
            self.disable_buttons()
            self.evolve_ids.append(self.evolve_button.after(int(self.config["evolution_delay"])*1000, lambda: self.evolve(p)))
        else:
            self.log_info("idle...")
            self.reset_windows()
        
    def transfer_pokemon(self):
        if self.data["transfer"]:
            p = self.data["transfer"][0]
            id = str(p.number)
            self.log_info('{0:<35} {1:<8} {2:<8.2%}'.format('transferring pokemon: '+str(p.name),str(p.cp),p.ivPercent,), "working")
            self.disable_buttons()
            self.transfer_ids.append(self.transfer_button.after(int(self.config["transfer_delay"])*1000, lambda: self.transfer(p)))
        else:
            self.log_info("idle...")
            self.reset_windows()
            
    def disable_buttons(self):
        self.transfer_button.config(state="disabled")
        self.evolve_button.config(state="disabled")
        
    def enable_buttons(self):
        self.transfer_button.config(state="normal")
        self.evolve_button.config(state="normal")
        
    def transfer(self, p):
        self.data.transfer_pokemon(p)
        self.enable_buttons()
        if self.data["transfer"]:
            self.transfer_pokemon()
        self.reset_windows()

    def evolve(self, p):
        self.data.evolve_pokemon(p)
        self.enable_buttons()
        if self.data["evolve"]:
            self.evolve_pokemon()
        self.reset_windows()
    
    def cancel_actions(self):
        for id in self.transfer_ids[:]:
            self.transfer_button.after_cancel(id)
            self.transfer_ids.remove(id)
        for id in self.evolve_ids[:]:
            self.evolve_button.after_cancel(id)
            self.evolve_ids.remove(id)
        self.enable_buttons()
        self.log_info("idle...")
        self.reset_windows()