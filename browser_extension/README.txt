Jarvis Tabs - lets Jarvis see and manage the tabs in your browser
==================================================================

What it does: when you ask Jarvis "summarize this", "what does the YouTube tab say", "what tabs do I have open",
"close the Reddit tab", "reopen the tab I just closed" or "switch to my email tab", Jarvis asks this extension, which
reads or changes the tabs inside your browser. It only talks to Jarvis on this PC (127.0.0.1); both sides prove they
know a secret pairing key first. Jarvis writes that key into pairing.json in this folder the first time it runs.

Install once (Jarvis must have run at least once, so pairing.json exists):

Opera GX (also Chrome / Edge / Brave)
  1. Open opera://extensions (Chrome: chrome://extensions, Edge: edge://extensions).
  2. Turn on "Developer mode" (top right).
  3. Click "Load unpacked" and choose this browser_extension folder.
  4. To let Jarvis read private windows too: on the extension's card click Details, then turn on
     "Allow in private mode" (Chrome: "Allow in Incognito").
  The browser may show a "developer mode extensions" notice at start-up: that's normal for an extension loaded this way.

Firefox
  - Quick test: open about:debugging#/runtime/this-firefox, click "Load Temporary Add-on" and pick manifest.json in this
    folder. Firefox removes temporary add-ons when it closes.
  - To keep it installed, Firefox needs the add-on signed by Mozilla (free, "unlisted" on addons.mozilla.org), or
    Firefox Developer Edition / ESR with xpinstall.signatures.required set to false in about:config.
  - Firefox asks for site access separately: in about:addons > Jarvis Tabs > Permissions, allow "Access your data for
    all websites", and under Details allow "Run in Private Windows" if you want those read.

It connects by itself within 30 seconds of Jarvis starting. Jarvis's dashboard lists it under Services ("browser tabs").
Pages it can't read: the browser's own pages (settings, extensions, new tab), the add-on stores, and tabs the browser
has put to sleep (open them once and ask again). If you change the port in Jarvis's Settings, restart Jarvis and then
click the reload button on the extension's card.
