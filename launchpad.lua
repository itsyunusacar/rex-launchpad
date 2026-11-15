-- rex-launchpad: a project launcher for Rex.
-- https://github.com/itsyunusacar/rex-launchpad
--
-- In ~/.config/rex/init.lua:
--   local launchpad = dofile(os.getenv("HOME") .. "/.config/rex/launchpad/launchpad.lua")
--   launchpad.setup{ root = "~/Projects" }

local M = {}

local HOME = os.getenv("HOME")
local HERE = (debug.getinfo(1, "S").source:gsub("^@", ""):match("^(/.*)/[^/]*$")) or (HOME .. "/.config/rex/launchpad")

local STRINGS = {
  en = {
    category = "Launchpad",
    panel    = "Launchpad…",
    open     = "Open Project",
    refresh  = "Refresh Projects",
    project  = "Project: ",
    label    = "Launchpad",
  },
  tr = {
    category = "Projeler",
    panel    = "Projeler…",
    open     = "Projeyi Aç",
    refresh  = "Projeleri Yenile",
    project  = "Proje: ",
    label    = "Projeler",
  },
}

local function expand(path)
  return (path:gsub("^~", HOME))
end

local function detect_lang()
  local r = rex.exec({ "defaults", "read", "-g", "AppleLanguages" })
  local first = r and r.ok and r.stdout:match('"?([%a%-]+)"?%s*[,)]')
  if first and first:sub(1, 2) == "tr" then return "tr" end
  return "en"
end

-- Claude Code keeps history per directory in ~/.claude/projects/<path with
-- every non-alphanumeric character replaced by "-">.
local function claude_command(dir)
  local hist = HOME .. "/.claude/projects/" .. dir:gsub("[^%w]", "-")
  local r = rex.exec({ "sh", "-c", 'ls "$0"/*.jsonl >/dev/null 2>&1', hist })
  local claude = (r and r.ok) and "claude --continue" or "claude"
  return { "sh", "-c", claude .. '; exec "${SHELL:-/bin/zsh}" -l' }
end

function M.setup(opts)
  opts = opts or {}
  local root   = expand(opts.root or "~/Projects")
  local key    = opts.key == nil and "cmd+o" or opts.key
  local claude = opts.claude ~= false
  local lang   = (opts.lang == nil or opts.lang == "auto") and detect_lang() or opts.lang
  local T      = STRINGS[lang] or STRINGS.en

  local function open_project(name)
    local dir = root .. "/" .. name
    local list, err = rex.call("session.list", {})
    if list == nil then error(err, 0) end
    local sid
    for _, s in ipairs(list.sessions or {}) do
      if s.label == name then sid = s.session_id break end
    end
    if sid == nil then
      local options = { cwd = dir }
      if claude then
        options.interactive = true
        options.command = claude_command(dir)
      end
      local created, cerr = rex.call("session.create", {
        label = name,
        initial_windows = { {
          window_label = name,
          layout = rex.layout.block{ flavor = "com.superlogical.terminal.shell", options = options },
        } },
      })
      if created == nil then error(cerr, 0) end
      sid = created.session_id
    end
    rex.client.queue("session.select", { session_id = sid })
    return { session_id = sid }
  end

  rex.action{
    name = "launchpad", title = T.panel, category = T.category,
    keywords = "launchpad project projects proje projeler open new",
    run  = function()
      local _, err = rex.session.new_layer{
        bounds = { 0.18, 0.1, 0.64, 0.72 },
        focus  = true,
        layout = rex.layout.block{
          flavor  = "com.superlogical.terminal.shell",
          label   = T.label,
          options = { command = { "python3", HERE .. "/launchpad.py", root, lang } },
        },
      }
      if err ~= nil then error(err, 0) end
    end,
  }

  rex.action{
    name = "launchpad_open", title = T.open, category = T.category,
    args = { name = "string" },
    run  = function(_, args) return open_project(args.name) end,
  }

  rex.action{
    name = "launchpad_refresh", title = T.refresh, category = T.category,
    run  = function() return rex.call("server.config_reload", {}) end,
  }

  -- One command palette entry per project folder.
  local r = rex.exec({ "find", root, "-mindepth", "1", "-maxdepth", "1", "-type", "d", "-not", "-name", ".*" })
  if r and r.ok then
    local names, used = {}, {}
    for line in r.stdout:gmatch("[^\n]+") do names[#names + 1] = line:match("([^/]+)$") end
    table.sort(names, function(a, b) return a:lower() < b:lower() end)
    for _, name in ipairs(names) do
      local id = "project_" .. name:lower():gsub("[^a-z0-9]+", "_"):gsub("_+$", "")
      while used[id] do id = id .. "_" end
      used[id] = true
      rex.action{
        name = id, title = T.project .. name, category = T.category,
        keywords = "project proje " .. name,
        run  = function() return open_project(name) end,
      }
    end
  end

  if key then rex.bind(key, "launchpad") end
end

return M
