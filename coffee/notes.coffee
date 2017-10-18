ipc = require('electron').ipcRenderer

window.test = (pagenumber) ->
    $("textarea#notes").html(pagenumber);

ipc.on 'test', (evt, p) -> window.test p
