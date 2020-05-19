clsMarkdown = require './js/classes/mds_markdown'
ipc = require('electron').ipcRenderer
md = require('markdown-it')();
Path        = require 'path'

resolvePathFromMarp = (path = './') -> Path.resolve(__dirname, './', path)

document.addEventListener 'DOMContentLoaded', ->
  $ = window.jQuery = window.$ = require('jquery')

  do ($) ->
  # First, resolve Marp resources path
  $("[data-marp-path-resolver]").each ->
    for target in $(@).attr('data-marp-path-resolver').split(/\s+/)
      $(@).attr(target, resolvePathFromMarp($(@).attr(target)))

  Markdown = new clsMarkdown({ afterRender: clsMarkdown.generateAfterRender($) })


  $('body').keydown (event) ->
    forwards = switch event.which
      when 81 # q
        $('body').toggleClass("laserpointer")
      when 87 # w
        $('#highlighter').toggle()
      when 69 # e
        $('#highlighter').height('+=' + if event.shiftKey then '10' else '5')
      when 82 # r
        $('#highlighter').height('-=' + if event.shiftKey then '10' else '5')

  themes = {}
  themes.current = -> $('#theme-css').attr('href')
  themes.default = themes.current()
  themes.apply = (path = null) ->
    toApply = resolvePathFromMarp(path || themes.default)

    if toApply isnt themes.current()
      $('#theme-css').attr('href', toApply)
      setTimeout applyScreenSize, 20

      return toApply.match(/([^\/]+)\.css$/)[1]
    false

  setStyle = (identifier, css) ->
    id  = "mds-#{identifier}Style"
    elm = $("##{id}")
    elm = $("<style id=\"#{id}\"></style>").appendTo(document.head) if elm.length <= 0
    elm.text(css)

  getCSSvar = (prop) -> document.defaultView.getComputedStyle(document.body).getPropertyValue(prop)

  getSlideSize = ->
    size =
      w: +getCSSvar '--slide-width'
      h: +getCSSvar '--slide-height'

    size.ratio = size.w / size.h
    size

  applySlideSize = (width, height) ->
    setStyle 'slideSize',
      """
      body {
        --slide-width: #{width || 'inherit'};
        --slide-height: #{height || 'inherit'};
      }
      """
    applyScreenSize()

  getScreenSize = ->
    size =
      w: document.documentElement.clientWidth
      h: document.documentElement.clientHeight

    previewMargin = +getCSSvar '--preview-margin'
    size.ratio = (size.w - previewMargin * 2) / (size.h - previewMargin * 2)
    size

  applyScreenSize = ->
    size = getScreenSize()
    setStyle 'screenSize', "body { --screen-width: #{size.w}; --screen-height: #{size.h}; }"
    $('#container').toggleClass 'height-base', size.ratio > getSlideSize().ratio

  applyCurrentPage = (page) ->
    setStyle 'currentPage',
      """
      @media not print {
        body.slide-view.screen .slide_wrapper:not(:nth-of-type(#{page})):not(:nth-of-type(#{page + 1})) {
          width: 0 !important;
          height: 0 !important;
          border: none !important;
          box-shadow: none !important;
        }

        body.slide-view.screen .slide_wrapper:nth-of-type(#{page}) {
          top: 25% !important;
        }

        body.slide-view.screen .slide_wrapper:nth-of-type(#{page + 1}) {
          top: 75% !important;
        }
      }
      """

  render = (md) ->
    applySlideSize md.settings.getGlobal('width'), md.settings.getGlobal('height')
    md.changedTheme = themes.apply md.settings.getGlobal('theme')

    $('#markdown').html(md.parsed)

    setImageDirectory = (dir) -> $('head > base').attr('href', dir || './')

    # Initialize
    $(document).on 'click', 'a', (e) ->
      e.preventDefault()
      ipc.sendToHost 'linkTo', $(e.currentTarget).attr('href')

    $(window).resize (e) -> applyScreenSize()
    applyScreenSize()

  ipc.on 'test', (evt, p) ->
    render(Markdown.parse(p));

  ipc.on 'changepage', (evt, p) ->
    applyCurrentPage(p);


