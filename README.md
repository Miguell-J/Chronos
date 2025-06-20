![GitHub repo size](https://img.shields.io/github/repo-size/Miguell-J/Chronos?style=for-the-badge)
![GitHub language count](https://img.shields.io/github/languages/count/Miguell-J/Chronos?style=for-the-badge)
![GitHub forks](https://img.shields.io/github/forks/Miguell-J/Chronos?style=for-the-badge)
![Bitbucket open issues](https://img.shields.io/bitbucket/issues/Miguell-J/Chronos?style=for-the-badge)
![Bitbucket open pull requests](https://img.shields.io/bitbucket/pr-raw/Miguell-J/Chronos?style=for-the-badge)

<h1 align="center">🕰Chronos</h1>
<p align="center">
  <b>Your own Git-powered version control system, fully built in Python.</b><br>
  <i>Hackable. Transparent. Educational. Powerful.</i>
</p>

![](/ch.png)

<p align="center">
  <img src="https://img.shields.io/badge/build-passing-brightgreen" />
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" />
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" />
</p>

---

## 🚀 What is Chronos?

**Chronos** is a custom-made, fully-featured Git-like version control system written entirely in Python.

It's designed to:

- 🧠 Teach you how Git works under the hood.
- ⚡ Provide a transparent, customizable CLI for managing code.
- 🧩 Extend Git with new ideas like **environment snapshots**.
- 💻 Serve as a foundation for new version control experiments.

Whether you're a hacker, student, researcher, or engineer — Chronos is your programmable time machine.

---

## ✨ Features

| Command              | Description                                                      |
|----------------------|------------------------------------------------------------------|
| `init`               | Initialize a Chronos repository (`.git`)                         |
| `add`, `rm`          | Stage or remove files                                            |
| `commit`             | Create a commit from staged files                               |
| `log`                | Print commit history as a Graphviz DAG                          |
| `status`             | Show changes (staged, unstaged, untracked)                      |
| `checkout`           | Restore files or switch branches                                |
| `hash-object`        | Compute object hashes, optionally storing them                  |
| `cat-file`           | Display content of stored Git-like objects                      |
| `ls-tree`            | List contents of tree objects (directories)                     |
| `tag`                | Lightweight or annotated tagging                                |
| `rev-parse`          | Parse refs into SHA-1s                                          |
| `show-ref`           | Show all references in the repository                           |
| `check-ignore`       | Evaluate `.gitignore` rules                                     |
| `ls-files`           | List all staged files                                           |
| **`branch`**(comming soon)         | Create, delete and list branches                                |
| **`merge`**(comming soon)          | Perform fast-forward or 3-way merges                            |
| **`snapshot`**(comming soon)       | Take environment snapshots (pip, OS, env vars, etc.)            |

---

## 🧪 Snapshot System (comming soon)

Chronos introduces the concept of version-controlled **environment snapshots**, storing:

- Python packages (`pip freeze`)
- OS and platform info
- Shell environment variables
- Git metadata
- System tools (`uname`, `sys.version`)

```bash
chronos snapshot -m "Training env for GPT model"
````

Stored as `.chronos/.snapshot_env` and committed automatically.

---

## 📁 Folder Structure

```bash
.git/
├── objects/
│   └── <sha-1> compressed git-like objects
├── refs/
│   ├── heads/       # Branches
│   └── tags/        # Tags
├── HEAD             # Symbolic or detached ref
├── index            # Binary staging area
└── config           # Repo metadata
```

All written and read in Python. No dependencies on Git internals.

---

## 🧱 How It Works

Chronos reimplements Git concepts from scratch:

* 🧩 `GitBlob`, `GitTree`, `GitCommit`, `GitTag` — as classes.
* 🧠 Custom object (de)serialization, hashing (`SHA-1 + zlib`).
* 📦 Fully binary index file (DIRC) parser and writer.
* 🔍 File metadata: uid, gid, perms, inode, size, etc.
* ⚙️ HEAD management, ref resolution, detached states.

---

## 📌 Example Usage

```bash
# Start a project
chronos init
chronos add main.py
chronos commit -m "Initial commit"

# Create and switch branches
chronos branch dev (comming soon)
chronos checkout dev

# Merge back into master
chronos checkout master
chronos merge dev (comming soon)

# Take an environment snapshot
chronos snapshot -m "AI experiment environment" (comming soon)
```

---

## 🔮 Roadmap

* [ ] `diff` support between working tree/index/HEAD
* [ ] Conflict resolution and manual merge tools
* [ ] `stash`, `rebase`, `revert`
* [ ] Chronos server: push/pull over HTTP
* [ ] TUI interface (like `lazygit`)
* [ ] Snapshots for datasets and models
* [ ] Visualization: commit graph renderer in SVG/HTML

---

## 🧠 Why Use Chronos?

| Feature             | Git     | Chronos        |
| ------------------- | ------- | -------------- |
| Language            | C       | Python         |
| Hackable            | ❌       | ✅              |
| Learnable Internals | ❌       | ✅ step-by-step |
| Snapshots           | ❌       | ✅ built-in     |
| Custom Commands     | Limited | Infinite       |
| Ideal for education | ❌       | ✅              |

Chronos was born to **educate**, **experiment**, and **push the boundaries** of version control.

---

## 🧪 For Developers & Hackers

The source code is fully modular and readable. You can:

* Extend commands
* Add new object types
* Replace storage format (ex: graph-based file system)
* Build visual tools on top

Check out `chronos.py` — every line is meant to be understood.

---

## 📜 License

MIT —> Use it, hack it, share it.

---

## 💡 Author

Made with ⚙️ and 🧠 by **Miguel Araújo Julio**
