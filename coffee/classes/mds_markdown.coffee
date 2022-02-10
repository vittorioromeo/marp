highlightJs  = require 'highlight.js'
pygmentsJs   = require 'pygments'
twemoji      = require 'twemoji'
extend       = require 'extend'
markdownIt   = require 'markdown-it'
Path         = require 'path'
MdsMdSetting = require './mds_md_setting'
{exist}      = require './mds_file'
strReplaceAll = require 'str-replace-all'
jsStringEscape = require 'js-string-escape'

module.exports = class MdsMarkdown
  @slideTagOpen:  (page) -> '<div class="slide_wrapper" id="' + page + '"><div class="slide"><div class="slide_bg"></div><div class="slide_inner">'
  @slideTagClose: (page) -> '</div><footer class="slide_footer"></footer><span class="slide_page" data-page="' + page + '">' + page + '</span></div></div>'

  @dict: {}
  @highlighter: (code, lang) ->
    if lang?
      if lang == 'text' or lang == 'plain'
        return ''
      else if lang == 'pcpp'
        if code of MdsMarkdown.dict
          return MdsMarkdown.dict[code]
        else
          res = pygmentsJs.colorizeSync(code, "cpp", 'html').substring(28).slice(0, -13)
          MdsMarkdown.dict[code] = res
          return res
      else if highlightJs.getLanguage(lang)
        try
          return highlightJs.highlight(lang, code, true).value

    highlightJs.highlightAuto(code).value

  @default:
    options:
      html: true
      xhtmlOut: true
      breaks: true
      linkify: true
      highlight: @highlighter

    plugins:
      'markdown-it-mark': {}
      'markdown-it-emoji':
        shortcuts: {}
      'markdown-it-katex': {}

    twemoji:
      base: Path.resolve(__dirname, '../../node_modules/twemoji/2') + Path.sep
      size: 'svg'
      ext: '.svg'

  @createMarkdownIt: (opts, plugins) ->
    md = markdownIt(opts)
    md.use(require(plugName), plugOpts ? {}) for plugName, plugOpts of plugins
    md

  @generateAfterRender: ($) ->
    (md) ->
      mdElm = $("<div>#{md.parsed}</div>")

      # Sanitize link tag
      mdElm.find('link:not([rel="stylesheet"])').remove()

      mdElm.find('p > img[alt~="bg"]').each ->
        $t  = $(@)
        p   = $t.parent()
        bg  = $t.parents('.slide_wrapper').find('.slide_bg')
        src = $t[0].src
        alt = $t.attr('alt')
        elm = $('<div class="slide_bg_img"></div>').css('backgroundImage', "url(#{src})").attr('data-alt', alt)

        for opt in alt.split(/\s+/)
          elm.css('backgroundSize', "#{m[1]}%") if m = opt.match(/^(\d+(?:\.\d+)?)%$/)

        elm.appendTo(bg)
        $t.remove()
        p.remove() if p.children(':not(br)').length == 0 && /^\s*$/.test(p.text())

      mdElm.find('img[alt*="%"]').each ->
        for opt in $(@).attr('alt').split(/\s+/)
          if m = opt.match(/^(\d+(?:\.\d+)?)%$/)
            $(@).css('zoom', parseFloat(m[1]) / 100.0)

      mdElm
        .children('.slide_wrapper')
        .each ->
          $t = $(@)

          # Page directives for themes
          page = $t[0].id
          for prop, val of md.settings.getAt(+page, false)
            $t.attr("data-#{prop}", val)
            $t.find('footer.slide_footer:last').text(val) if prop == 'footer'

          # Detect "only-***" elements
          inner = $t.find('.slide > .slide_inner')
          innerContents = inner.children().filter(':not(base, link, meta, noscript, script, style, template, title)')

          headsLength = inner.children(':header').length
          $t.addClass('only-headings') if headsLength > 0 && innerContents.length == headsLength

          quotesLength = inner.children('blockquote').length
          $t.addClass('only-blockquotes') if quotesLength > 0 && innerContents.length == quotesLength

      md.parsed = mdElm.html()

  rulers: []
  settings: new MdsMdSetting
  afterRender: null
  twemojiOpts: {}

  constructor: (settings) ->
    opts         = extend({}, MdsMarkdown.default.options, settings?.options || {})
    plugins      = extend({}, MdsMarkdown.default.plugins, settings?.plugins || {})
    @twemojiOpts = extend({}, MdsMarkdown.default.twemoji, settings?.twemoji || {})
    @afterRender = settings?.afterRender || null
    @markdown    = MdsMarkdown.createMarkdownIt.call(@, opts, plugins)
    @afterCreate()

  afterCreate: =>
    md      = @markdown
    {rules} = md.renderer

    defaultRenderers =
      image:      rules.image
      html_block: rules.html_block

    extend rules,
      emoji: (token, idx) =>
        if @mustfindrulers == false
          twemoji.parse(token[idx].content, @twemojiOpts)

      hr: (token, idx) =>
        if @mustfindrulers == true
          @_rulers.push token[idx].map[0]
        else
          ++@lastruler
          "#{MdsMarkdown.slideTagClose(@lastruler)}#{MdsMarkdown.slideTagOpen(@lastruler + 1)}"

      image: (args...) =>
        if @mustfindrulers == false
          @renderers.image.apply(@, args)
          defaultRenderers.image.apply(@, args)

      html_block: (args...) =>
        if @mustfindrulers == false
          @renderers.html_block.apply(@, args)
          defaultRenderers.html_block.apply(@, args)

  parse: (markdown) =>
    @_rulers = []

    # console.log @_rulers

    # Rendering step to find slide separators
    @mustfindrulers = true
    @markdown.render markdown
    @mustfindrulers = false
    @lastruler = 0

    final_script  = "const include = require('require-reload')(require);"
    final_script += '(function() {\nlet out = "";\n'

    line = ''
    i = 0
    while i < markdown.length
      if markdown[i] == '\n'
        if line.startsWith('@@ ')
          final_script += "#{line.substr(3, line.length)}\n"
        else
          final_script += "out += '#{jsStringEscape line}\\n';\n"
        line = ''
      else if markdown.startsWith('@{{', i)
        for j in [(i)...(markdown.length)]
          if markdown.startsWith('}}', j)
            js_value = markdown.substring(i + 3, j)
            # console.log("js_value: #{js_value}")
            final_script += "out += #{js_value};\n"
            i = j + 1
            break
      else if markdown.startsWith('@[[', i)
        for j in [(i)...(markdown.length)]
          if markdown.startsWith(']]', j)
            js_value = markdown.substring(i + 3, j)
            js_value = js_value.replace(/\n/g, "\\n");
            # console.log("js_value: #{js_value}")
            final_script += "out += #{js_value};\n"
            i = j + 1
            break
      else
        line += markdown[i]

      i += 1

    final_script += "out += '#{jsStringEscape line}\\n';\n"
    line = ''

    final_script += 'return out;\n})();'
    # console.log(final_script)
    # console.log(eval(final_script))
    markdown = eval(final_script)

    @_settings        = new MdsMdSetting
    @settingsPosition = []
    @lastParsed       = """
                        #{MdsMarkdown.slideTagOpen(1)}
                        #{@markdown.render markdown}
                        #{MdsMarkdown.slideTagClose(@_rulers.length + 1)}
                        """
    ret =
      parsed: @lastParsed
      settingsPosition: @settingsPosition
      rulerChanged: @rulers.join(",") != @_rulers.join(",")

    @rulers   = ret.rulers   = @_rulers
    @settings = ret.settings = @_settings

    @afterRender(ret) if @afterRender?
    ret

  renderers:
    image: (tokens, idx, options, env, self) ->
      src = decodeURIComponent(tokens[idx].attrs[tokens[idx].attrIndex('src')][1])
      tokens[idx].attrs[tokens[idx].attrIndex('src')][1] = src if exist(src)

    html_block: (tokens, idx, options, env, self) ->
      {content} = tokens[idx]
      return if content.substring(0, 3) isnt '<!-'

      if matched = /^(<!-{2,}\s*)([\s\S]*?)\s*-{2,}>$/m.exec(content)
        spaceLines = matched[1].split("\n")
        lineIndex  = tokens[idx].map[0] + spaceLines.length - 1
        startFrom  = spaceLines[spaceLines.length - 1].length

        for mathcedLine in matched[2].split("\n")
          parsed = /^(\s*)(([\$\*]?)(\w+)\s*:\s*(.*))\s*$/.exec(mathcedLine)

          if parsed
            startFrom += parsed[1].length
            pageIdx = @lastruler

            if parsed[3] is '$'
              @_settings.setGlobal parsed[4], parsed[5]
            else
              @_settings.set pageIdx + 1, parsed[4], parsed[5], parsed[3] is '*'

            @settingsPosition.push
              pageIdx: pageIdx
              lineIdx: lineIndex
              from: startFrom
              length: parsed[2].length
              property: "#{parsed[3]}#{parsed[4]}"
              value: parsed[5]

          lineIndex++
          startFrom = 0
