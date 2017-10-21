ipc = require('electron').ipcRenderer
md = require('markdown-it')();

window.test = (pagenumber) ->
    $("#notes").html(md.render(pagenumber));

ipc.on 'test', (evt, p) -> window.test p

$("#tless").click(() ->
    $("#notes").css('font-size', '-=1'))

$("#tmore").click(() ->
    $("#notes").css('font-size', '+=1'))
