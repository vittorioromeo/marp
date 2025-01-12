module.exports = gulp = require('gulp')

$           = do require('gulp-load-plugins')
config      = require('./package.json')
del         = require('del')
packager    = require('electron-packager')
runSequence = require('run-sequence')
Path        = require('path')
extend      = require('extend')
mkdirp      = require('mkdirp')
$.uglify    = require('gulp-uglify-es').default;

packageOpts =
  asar: true
  dir: 'dist'
  out: 'packages'
  name: config.productName
  version: config.devDependencies['electron']
  prune: false
  overwrite: true
  'app-bundle-id': 'jp.yhatt.marp'
  'app-version': config.version
  'version-string':
    ProductName: config.productName
    InternalName: config.productName
    FileDescription: config.productName
    CompanyName: 'yhatt'
    LegalCopyright: ''
    OriginalFilename: "#{config.productName}.exe"

packageElectron = (opts = {}, done) ->
  packager extend(packageOpts, opts), (err) ->
    if err
      if err.syscall == 'spawn wine'
        $.util.log 'Packaging failed. Please install wine.'
      else
        throw err

    done() if done?

globFolders = (pattern, func, callback) ->
  doneTasks = 0
  g = new (require("glob").Glob) pattern, (err, pathes) ->
    throw err if err
    done = ->
      doneTasks++
      callback() if callback? and doneTasks >= pathes.length

    if pathes.length > 0
      func(path, done) for path in pathes
    else
      callback()

gulp.task 'clean:js', -> del ['js/**/*', 'js']
gulp.task 'clean:css', -> del ['css/**/*', 'css']
gulp.task 'clean:dist', -> del ['dist/**/*', 'dist']
gulp.task 'clean:packages', -> del ['packages/**/*', 'packages']
gulp.task 'clean:releases', -> del ['releases/**/*', 'releases']
gulp.task 'clean', (gulp.series 'clean:js', 'clean:css', 'clean:dist', 'clean:packages')

sass = require('gulp-sass')(require('sass'))

gulp.task 'compile:coffee', ->
  gulp.src 'coffee/**/*.coffee'
    .pipe $.plumber()
    .pipe $.sourcemaps.init()
    .pipe $.coffee
      bare: true
    .pipe $.uglify()
    .pipe $.sourcemaps.write()
    .pipe gulp.dest('js')

gulp.task 'compile:sass', ->
  gulp.src ['sass/**/*.scss', 'sass/**/*.sass']
    .pipe $.plumber()
    .pipe $.sourcemaps.init()
    .pipe sass()
    .pipe $.sourcemaps.write()
    .pipe gulp.dest('css')
  gulp.src ['resources/katex/fonts/*']
    .pipe gulp.dest('css/fonts')

gulp.task 'compile:coffee:production', gulp.series 'clean:js', ->
  gulp.src 'coffee/**/*.coffee'
    .pipe $.coffee
      bare: true
    .pipe $.uglify()
    .pipe gulp.dest('js')

gulp.task 'compile:sass:production', gulp.series 'clean:css', ->
  gulp.src ['sass/**/*.scss', 'sass/**/*.sass']
    .pipe sass()
    .pipe $.cssnano
      zindex: false
    .pipe gulp.dest('css')
  gulp.src ['resources/katex/fonts/*']
    .pipe gulp.dest('css/fonts')

gulp.task 'compile', (gulp.series 'compile:coffee', 'compile:sass')
gulp.task 'compile:production', (gulp.series 'compile:coffee:production', 'compile:sass:production')

gulp.task 'dist', gulp.series 'clean:dist', ->
  gulp.src([
    'js/**/*'
    'css/**/*'
    'images/**/*'
    'examples/**/*'
    '*.js'
    '!gulpfile.js'
    '*.html'
    'package.json'
    'example.md'
    'LICENSE'
    'yarn.lock'
  ], { base: '.' })
    .pipe gulp.dest('dist')
    .pipe $.install
      commands:
        'package.json': 'yarn'
      yarn: ['--production', '--ignore-optional', '--no-bin-links']

gulp.task 'package', (gulp.series 'clean:packages', 'dist'), (done) ->
  runSequence 'package:win32', 'package:darwin', 'package:linux', done

gulp.task 'package:win32', ->
  packageElectron {
    platform: 'win32'
    arch: 'ia32,x64'
    icon: Path.join(__dirname, 'resources/windows/marp.ico')
  }
gulp.task 'package:linux', ->
  packageElectron {
    platform: 'linux'
    arch: 'ia32,x64'
  }
gulp.task 'package:darwin', ->
  packageElectron {
    platform: 'darwin'
    arch: 'x64'
    icon: Path.join(__dirname, 'resources/darwin/marp.icns')
  }, ->
    gulp.src ["packages/*-darwin-*/#{config.productName}.app/Contents/Info.plist"], { base: '.' }
      .pipe $.plist
        CFBundleDocumentTypes: [
          {
            CFBundleTypeExtensions: ['md', 'mdown']
            CFBundleTypeIconFile: ''
            CFBundleTypeName: 'Markdown file'
            CFBundleTypeRole: 'Editor'
            LSHandlerRank: 'Owner'
          }
        ]
      .pipe gulp.dest('.')

gulp.task 'build',        (done) -> runSequence 'compile:production', 'package', done
gulp.task 'build:win32',  (done) -> runSequence 'compile:production', 'dist', 'package:win32', done
gulp.task 'build:linux',  (done) -> runSequence 'compile:production', 'dist', 'package:linux', done
gulp.task 'build:darwin', (done) -> runSequence 'compile:production', 'dist', 'package:darwin', done


gulp.task 'archive:win32', (done) ->
  globFolders 'packages/*-win32-*', (path, globDone) ->
    gulp.src ["#{path}/**/*"]
      .pipe $.zip("#{config.version}-#{Path.basename(path, '.*')}.zip")
      .pipe gulp.dest('releases')
      .on 'end', globDone
  , done

gulp.task 'archive:darwin', (done) ->
  appdmg = try
    require('appdmg')
  catch err
    null

  unless appdmg
    $.util.log 'Archiving for darwin is supported only macOS.'
    return done()

  globFolders 'packages/*-darwin-*', (path, globDone) ->
    release_to = Path.join(__dirname, "releases/#{config.version}-#{Path.basename(path, '.*')}.dmg")

    mkdirp Path.dirname(release_to), (err) ->
      del(release_to)
        .then ->
          running_appdmg = appdmg {
            target: release_to
            basepath: Path.join(__dirname, path)
            specification:
              title: config.productName
              background: Path.join(__dirname, "resources/darwin/dmg-background.png")
              'icon-size': 80
              window: {
                position: { x: 90, y: 90 }
                size: { width: 624, height: 412 }
              }
              contents: [
                { x: 210, y: 300, type: 'file', path: "#{config.productName}.app" }
                { x: 410, y: 300, type: 'link', path: '/Applications' }
              ]
          }
          running_appdmg.on 'finish', globDone
  , done

gulp.task 'archive:linux', (done) ->
  globFolders 'packages/*-linux-*', (path, globDone) ->
    gulp.src ["#{path}/**/*"]
      .pipe $.tar("#{config.version}-#{Path.basename(path, '.*')}.tar")
      .pipe $.gzip()
      .pipe gulp.dest('releases')
      .on 'end', globDone
  , done


gulp.task 'archive', (gulp.series 'archive:win32', 'archive:darwin', 'archive:linux')

gulp.task 'release', (done) -> runSequence 'build', 'archive', 'clean', done
