###
Build scripts for Fancytree
###

"use strict"

module.exports = (grunt) ->

  grunt.initConfig

    pkg:
        grunt.file.readJSON("package.json")

    # Project metadata, used by the <banner> directive.
    meta:
        banner: "/*! <%= pkg.title || pkg.name %> - @VERSION - @DATE\n" +
                # "<%= grunt.template.today('yyyy-mm-dd HH:mm') %>\n" +
                "<%= pkg.homepage ? '  * ' + pkg.homepage + '\\n' : '' %>" +
                "  * Copyright (c) <%= grunt.template.today('yyyy') %> <%= pkg.author.name %>;" +
                " Licensed <%= _.map(pkg.licenses, 'type').join(', ') %>\n" +
                " */\n"
        # separator: "\n/*! --- Fancytree Plugin --- */\n"

    clean:
        build:
            src: [ "build" ]
        dist:
            src: [ "dist" ]
        post_build:  # Remove unwanted files from build folder
            src: [
              "build/jquery.fancytree.*.min.js"
              "build/jquery.fancytree.js"
              "build/jquery-ui-dependencies/"
            ]

    concat:
        core_to_build:
            options:
                stripBanners: true
            src: ["<banner:meta.banner>"
                  "src/jquery.fancytree.js"
                  ]
            dest: "build/jquery.fancytree.js"
        bundle_to_build:
            options:
                stripBanners: true
            src: [
                "<%= meta.banner %>"
                "src/jquery.fancytree.js"
                # "src/jquery.fancytree.ariagrid.js"
                "src/jquery.fancytree.childcounter.js"
                "src/jquery.fancytree.clones.js"
                # "src/jquery.fancytree.columnview.js"
                "src/jquery.fancytree.dnd.js"
                "src/jquery.fancytree.dnd5.js"
                "src/jquery.fancytree.edit.js"
                "src/jquery.fancytree.filter.js"
                # "src/jquery.fancytree.fixed.js"
                "src/jquery.fancytree.glyph.js"
                # "src/jquery.fancytree.grid.js"
                "src/jquery.fancytree.gridnav.js"
                "src/jquery.fancytree.multi.js"
                "src/jquery.fancytree.persist.js"
                "src/jquery.fancytree.table.js"
                "src/jquery.fancytree.themeroller.js"
                "src/jquery.fancytree.wide.js"
                ]
            dest: "build/jquery.fancytree-all.js"

        amd_bundle_min:
            options:
                banner: "<%= meta.banner %>"
                stripBanners: true
                process: (src, fspec) ->
                  # Remove all comments, including /*! ... */
                  src = src.replace(/\/\*(.|\n)*\*\//g, "")
                  if /fancytree..+.min.js/.test(fspec)
                    # If it is an extension:
                    # Prepend a one-liner instead
                    fspec = fspec.substr(6) # strip 'build/'
                    src = "\n/*! Extension '" + fspec + "' */" + src
                  return src
            src: [
                "lib/amd-intro-require-native-ui.js"
                "build/jquery.fancytree.min.js"
                # "build/jquery.fancytree.ariagrid.min.js"
                "build/jquery.fancytree.childcounter.min.js"
                "build/jquery.fancytree.clones.min.js"
                # "build/jquery.fancytree.columnview.min.js"
                "build/jquery.fancytree.dnd.min.js"
                "build/jquery.fancytree.dnd5.min.js"
                "build/jquery.fancytree.edit.min.js"
                "build/jquery.fancytree.filter.min.js"
                # "build/jquery.fancytree.fixed.min.js"
                "build/jquery.fancytree.glyph.min.js"
                # "build/jquery.fancytree.grid.min.js"
                "build/jquery.fancytree.gridnav.min.js"
                "build/jquery.fancytree.multi.min.js"
                "build/jquery.fancytree.persist.min.js"
                "build/jquery.fancytree.table.min.js"
                "build/jquery.fancytree.themeroller.min.js"
                "build/jquery.fancytree.wide.min.js"
                "lib/amd-outro.js"
                ]
            dest: "build/jquery.fancytree-all.min.js"

        all_deps:  # un-minified, so we can generate a map file
            options:
                banner: "<%= meta.banner %>"
                stripBanners: true
                process: (src, fspec) ->
                  # Remove all comments, including /*! ... */
                  # (but keep disclaimer for jQuery-UI)
                  # if not /jquery-ui..+.js/.test(fspec)
                  # # if not /jquery-ui..+.min.js/.test(fspec)
                  #     src = src.replace(/\/\*(.|\n)*\*\//g, "")
                  # # strip out AMD related code from jQuery-UI and make it an IIFE
                  # if /jquery-ui..+.min.js/.test(fspec)
                  #     src = src.replace(/\(function.+jQuery\)}\)\((.+\)}\)})\);/, "!$1(jQuery);")
                  if /jquery.fancytree.js/.test(fspec)
                      src = "\n/*! Fancytree Core */" + src
                  if /fancytree..+.js/.test(fspec)
                    # If it is an extension:
                    # Prepend a one-liner instead
                    fspec = fspec.substr(4) # strip 'src/'
                    src = "\n/*! Extension '" + fspec + "' */" + src
                  return src
            src: [
                "<%= meta.banner %>"
                # Inline jQuery UI custom (AMD header removed: IIFE only)
                "src/jquery-ui-dependencies/jquery-ui-iife.js"
                # Fancytree core and extensions, wrapped in UMD pattern
                "lib/amd-intro-require-jquery.js"
                "src/jquery.fancytree.js"
                # "src/jquery.fancytree.ariagrid.js"
                "src/jquery.fancytree.childcounter.js"
                "src/jquery.fancytree.clones.js"
                # "src/jquery.fancytree.columnview.js"
                # "src/jquery.fancytree.dnd.js"  # Draggable widget is not part of our custom jQuery UI dependencies
                "src/jquery.fancytree.dnd5.js"
                "src/jquery.fancytree.edit.js"
                "src/jquery.fancytree.filter.js"
                # "src/jquery.fancytree.fixed.js"
                "src/jquery.fancytree.glyph.js"
                # "src/jquery.fancytree.grid.js"
                "src/jquery.fancytree.gridnav.js"
                "src/jquery.fancytree.multi.js"
                "src/jquery.fancytree.persist.js"
                "src/jquery.fancytree.table.js"
                "src/jquery.fancytree.themeroller.js"
                "src/jquery.fancytree.wide.js"
                "lib/amd-outro.js"
                ]
            dest: "build/jquery.fancytree-all-deps.js"

    connect:
        forever:
            options:
                port: 8080
                base: "./"
                keepalive: true
        dev: # pass on, so subsequent tasks (like watch) can start
            options:
                port: 8080
                base: "./"
                keepalive: false
                # middleware: (connect) ->
                #     return [
                #         (req, res, next) ->
                #             res.setHeader('Access-Control-Allow-Origin', '*')
                #             res.setHeader('Access-Control-Allow-Methods', '*')
                #             next()
                #     ]
        sauce:  # Used by sauce tasks, see https://wiki.saucelabs.com/display/DOCS/Grunt-Saucelabs+Set+Up%2C+Configuration%2C+and+Usage
            options:
                # hostname: "localhost"
                # hostname: "127.0.0.1"
                # port: 8080
                port: 9999
                base: ""
                keepalive: false
        localhost_9999:  # Start web server for Sauce live testing w/ manuallly run bin/sc.exe
            options:
                # hostname: "localhost"
                port: 9999
                base: ""
                keepalive: true

    copy:
        build:  # Copy development files to build folder
            files: [{  # src/ => build/
                expand: true  # required for cwd
                cwd: "src/"
                src: [
                    "skin-**/*.{css,gif,md,png,less}"
                    "skin-common.less"
                    "*.txt"
                    ]
                dest: "build/"
            }, {  # src/ => build/modules/
                expand: true
                cwd: "src/"
                src: [ "jquery.*.js" ]
                dest: "build/modules/"
            }, {  # Top-level => build/
                src: ["LICENSE.txt"]
                dest: "build/"
            }]
        ui_deps:  #
            files: [{
                src: "src/jquery-ui-dependencies/jquery.fancytree.ui-deps.js"
                dest: "build/modules/jquery.fancytree.ui-deps.js"
            }]
        dist:  # Copy build folder to dist/ (recursive)
            files: [
              {expand: true, cwd: "build/", src: ["**"], dest: "dist/"}
            ]

    cssmin:
        options:
          report: "min"
        build:
            expand: true
            cwd: "build/"
            src: ["**/*.fancytree.css", "!*.min.css"]
            dest: "build/"
            ext: ".fancytree.min.css"

    devUpdate:
        main:
            options:
                reportUpdated: true
                updateType: 'prompt'  # 'report'

    docco:
        docs:
            src: ["src/jquery.fancytree.childcounter.js"]
            options:
                output: "doc/annotated-src"

    eslint:
        options:
            maxWarnings: 100
            # format: "stylish"
        # options:
        #   # See https://github.com/sindresorhus/grunt-eslint/issues/119
        #   quiet: true
        # We have to explicitly declare "src" property otherwise "newer"
        # task wouldn't work properly :/
        build:
            options:
                ignore: false
            src: [
              "build/jquery.fancytree.js"
              "build/jquery.fancytree-all.js"
              "build/modules/*.js"
              ]
        dev:
            src: [
              "src/*.js"
              "3rd-party/**/jquery.fancytree.*.js"
              # "test/**/test-*.js"
              "demo/**/*.js"
              ]
        fix:
            options:
                fix: true
            src: [
              "src/*.js"
              "3rd-party/**/jquery.fancytree.*.js"
              # "test/**/test-*.js"
              "demo/**/*.js"
              ]

    exec:
        upload:
            # FTP upload the demo files (requires https://github.com/mar10/pyftpsync)
            stdin: true  # Allow interactive console
            cmd: "pyftpsync upload . ftp://www.wwwendt.de/tech/fancytree --progress --exclude build,node_modules,.*,_* --delete-unmatched"
        upload_force:
            # FTP upload the demo files (requires https://github.com/mar10/pyftpsync)
            cmd: "pyftpsync upload . ftp://www.wwwendt.de/tech/fancytree --progress --exclude build,node_modules,.*,_* --delete-unmatched --resolve=local --force"

    jsdoc:
        build:
            src: ["src/*.js", "doc/README.md"]
            options:
                destination: "doc/jsdoc"
                template: "bin/jsdoc3-moogle",
                configure: "doc/jsdoc.conf.json"
                verbose: true

    less:
        development:
            options:
#               paths: ["src/"]
#               report: "min"
                compress: false
                yuicompress: false
#               optimization: 10

                # webpack uses /dist/skin-common.less as root path
                # grunt-less uses /dist/skin-Xxx/ui.fancyree.less as root path
                # So we define our theme LESS files for webpack compatibility
                # and fix it for grunt-less here:
                rootpath: ".."
            files: [
                {expand: true, cwd: "src/", src: "**/ui.fancytree.less", dest: "src/", ext: ".fancytree.css"}
            ]

    qunit:
        options:
            httpBase: "http://localhost:8080"
            # httpBase: "http://127.0.0.1:8080"
        build: [
            "test/unit/test-core-build.html"
        ]
        develop: [
            "test/unit/test-core.html"
            "test/unit/test-ext-filter.html"
            "test/unit/test-ext-table.html"
            "test/unit/test-ext-misc.html"
        ]
        dist: [
            "test/unit/test-core-dist.html"
        ]

    replace: # grunt-text-replace
        production:
            src: ["build/**/*.{js,less,css}"]
            overwrite : true
            replacements: [ {
                from : /@DATE/g
                # https://github.com/felixge/node-dateformat
                to : "<%= grunt.template.today('isoUtcDateTime') %>"
            },{
                from : /buildType:\s*\"[a-zA-Z]+\"/g
                to : "buildType: \"production\""
            },{
                from : /debugLevel:\s*[0-9]/g
                to : "debugLevel: 3"
            } ]
        release:
            src: ["dist/**/*.{js,less,css}"]
            overwrite : true
            replacements: [ {
                from : /@VERSION/g
                to : "<%= pkg.version %>"
            } ]

    "saucelabs-qunit":
        options:
            build: process.env.TRAVIS_JOB_ID
            throttled: 5
            framework: "qunit"
            # Map of extra parameters to be passed to sauce labs. example:
            #   {'video-upload-on-pass': false, 'idle-timeout': 60}
            sauceConfig:
              "video-upload-on-pass": false
              recordVideo: true
              # Needed for Edge/Windows (as of 2019-06-02) and Firefox(?)
              iedriverVersion: "3.141.59"
              seleniumVersion: "3.141.59"
            # Array of optional arguments to be passed to the Sauce Connect tunnel.
            # See https://saucelabs.com/docs/additional-config
            tunnelArgs: [
              '-v',
              '--logfile', 'saucelabs-tunnel.log',
              '--tunnel-domains', 'localhost,travis.dev'
              # '--direct-domains', 'google.com'
              ]

        triage:
            options:
                testname: "Triage"
                build: "triage"
                # urls: ["http://wwwendt.de/tech/fancytree/test/unit/test-core.html"]
                # urls: ["http://127.0.0.1:9999/test/unit/test-jQuery19-ui19.html"]
                # urls: ["http://127.0.0.1:9999/test/unit/test-jQuery1x-mig-ui1x.html"]
                urls: ["http://localhost:9999/test/unit/test-core.html"]
                # urls: ["http://127.0.0.1:9999/test/unit/test-core.html"]
                # tunneled: false  # Use bin/sc manually
                browsers: [
                  # Issue #825
                  # { browserName: "chrome", version: "dev", platform: "Windows 10" }
                  # { browserName: "internet explorer", version: "9", platform: "Windows 7" }
                  # { browserName: "internet explorer", version: "8", platform: "Windows 7" }
                  # { browserName: "chrome", version: "latest", platform: "Windows 10" }
                  # { browserName: "microsoftedge", version: "latest", platform: "Windows 10" }
                  # { browserName: "safari", version: "12", platform: "macOS 10.14" }
                  { browserName: "firefox", version: "latest", platform: "Windows 10" }
                ]

        ui_112:
            options:
                testname: "Fancytree qunit tests (jQuery 3, jQuery UI 1.12)"
                # urls: ["http://wwwendt.de/tech/fancytree/test/unit/test-core.html"]
                urls: ["http://localhost:9999/test/unit/test-core.html"]
                # urls: ["http://127.0.0.1:9999/test/unit/test-core.html"]
                # jQuery 3        supports IE 9+ and latest Chrome/Edge/Firefox/Safari (-1)
                # jQuery UI 1.12  supports IE 11 and latest Chrome/Edge/Firefox/Safari (-1)
                browsers: [
                  { browserName: "chrome", version: "latest", platform: "Windows 10" }
                  { browserName: "chrome", version: "latest-1", platform: "Windows 10" }
                  { browserName: "firefox", version: "latest", platform: "Windows 10" }
                  { browserName: "firefox", version: "latest-1", platform: "Windows 10" }
                  { browserName: "firefox", version: "latest", platform: "Linux" }
                  { browserName: "microsoftedge", version: "latest", platform: "Windows 10" }
                  { browserName: "microsoftedge", version: "latest-1", platform: "Windows 10" }
                  { browserName: "internet explorer", version: "11", platform: "Windows 8.1" }
                  { browserName: "internet explorer", version: "10", platform: "Windows 8" }
                  { browserName: "internet explorer", version: "9", platform: "Windows 7" }
                  # Test Saucelabs:
                  # { browserName: "chrome", version: "latest", platform: "macOS 10.14" }
                  # { browserName: "firefox", version: "latest", platform: "macOS 10.14" }

                ]
        # ui_111:
        #     options:
        #         testname: "Fancytree qunit tests (jQuery 1.11, jQuery UI 1.11)"
        #         # urls: ["http://wwwendt.de/tech/fancytree/test/unit/test-jQuery111-ui111.html"]
        #         urls: ["http://127.0.0.1:9999/test/unit/test-jQuery111-ui111.html"]
        #         # jQuery 1.11     supports IE + and latest Chrome/Edge/Firefox/Safari (-1)
        #         # jQuery UI 1.11  supports IE 7+ and ?
        #         browsers: [
        #           { browserName: "internet explorer", version: "10", platform: "Windows 8" }
        #           # Issue #842:
        #           # { browserName: "safari", version: "7", platform: "OS X 10.9" }
        #           { browserName: "safari", version: "8", platform: "OS X 10.10" }
        #         ]
        # ui_110:
        #     options:
        #         testname: "Fancytree qunit tests (jQuery 1.10, jQuery UI 1.10)"
        #         # urls: ["http://wwwendt.de/tech/fancytree/test/unit/test-jQuery110-ui110.html"]
        #         urls: ["http://127.0.0.1:9999/test/unit/test-jQuery110-ui110.html"]
        #         # jQuery 1.10    dropped support for IE 6
        #         # jQuery UI 1.10 supports IE 7+ and ?
        #         browsers: [
        #           # { browserName: "internet explorer", version: "8", platform: "Windows 7" }
        #           { browserName: "internet explorer", version: "9", platform: "Windows 7" }
        #         ]
        beta:  # This tests are allowed to fail in the travis matrix
            options:
                testname: "Fancytree qunit tests ('dev' browser versions)"
                # urls: ["http://wwwendt.de/tech/fancytree/test/unit/test-core.html"]
                urls: ["http://localhost:9999/test/unit/test-core.html"]
                # urls: ["http://127.0.0.1:9999/test/unit/test-core.html"]
                browsers: [
                  # Issue #825
                  { browserName: "chrome", version: "dev", platform: "Windows 10" }  #, chromedriverVersion: "2.46.0" }
                  # FF.dev is problematic: https://support.saucelabs.com/hc/en-us/articles/225253808-Firefox-Dev-Beta-Browser-Won-t-Start
                  { browserName: "firefox", version: "dev", platform: "Windows 10" }
                  # 2019-06-02: known problem with Saucelabs using localhost on macOS:
                  { browserName: "safari", version: "12", platform: "macOS 10.14" }
                  { browserName: "safari", version: "11", platform: "macOS 10.13" }
                  { browserName: "safari", version: "10", platform: "macOS 10.12" }
                  { browserName: "safari", version: "9", platform: "OS X 10.11" }
                  # { browserName: "safari", version: "8", platform: "OS X 10.10" }
                ]

    uglify:
        src_to_build:
            options:  # see https://github.com/gruntjs/grunt-contrib-uglify/issues/366
                report: "min"
                # preserveComments: "some"
                preserveComments: /(?:^!|@(?:license|preserve|cc_on))/
                output:
                    ascii_only: true  # #815
            files: [
              {
                  src: ["**/jquery.fancytree*.js", "!*.min.js"]
                  cwd: "src/"
                  dest: "build/"
                  expand: true
                  rename: (dest, src) ->
                      folder = src.substring(0, src.lastIndexOf("/"))
                      filename = src.substring(src.lastIndexOf("/"), src.length)
                      filename  = filename.substring(0, filename.lastIndexOf("."))
                      return dest + folder + filename + ".min.js"
              }
              ]

        all_deps:
            options:  # see https://github.com/gruntjs/grunt-contrib-uglify/issues/366
                report: "min"
                sourceMap: true
                # preserveComments: "some"
                preserveComments: /(?:^!|@(?:license|preserve|cc_on))/
                output:
                    ascii_only: true  # #815
            files: [
              {
                  src: ["jquery.fancytree-all-deps.js"]
                  cwd: "build/"
                  dest: "build/"
                  expand: true
                  rename: (dest, src) ->
                      folder = src.substring(0, src.lastIndexOf("/"))
                      filename = src.substring(src.lastIndexOf("/"), src.length)
                      filename  = filename.substring(0, filename.lastIndexOf("."))
                      return dest + folder + filename + ".min.js"
              }
              ]

    watch:
        less:
            files: "src/**/*.less"
            tasks: ["less:development"]
        eslint:
            options:
                atBegin: true
            files: ["src/*.js", "test/unit/*.js", "demo/**/*.js"]
            tasks: ["eslint:dev"]

    yabs:
        release:
            common: # defaults for all tools
              manifests: ['package.json', 'bower.json']
            # The following tools are run in order:
            run_test: { tasks: ['test'] }
            check: { branch: ['master'], canPush: true, clean: true, cmpVersion: 'gte' }
            bump: {} # 'bump' also uses the increment mode `yabs:release:MODE`
            run_build: { tasks: ['make_dist'] }
            commit: { add: '.' }
            tag: {}
            push: { tags: true, useFollowTags: true },
            githubRelease:
              repo: 'mar10/fancytree'
              draft: false
            npmPublish: {}
            bump_develop: { inc: 'prepatch' }
            commit_develop: { message: 'Bump prerelease ({%= version %}) [ci skip]' }
            push_develop: {}

  # ----------------------------------------------------------------------------


  # Load "grunt*" dependencies

  for key of grunt.file.readJSON("package.json").devDependencies
      grunt.loadNpmTasks key  if key isnt "grunt" and key.indexOf("grunt") is 0

  # Register tasks

  grunt.registerTask "server", ["connect:forever"]
  grunt.registerTask "dev", ["connect:dev", "watch"]
  # grunt.registerTask "prettier", ["eslint:fix"]
  grunt.registerTask "format", ["eslint:fix"]
  grunt.registerTask "test", [
      "eslint:dev",
      # "csslint",
      # "htmllint",
      "connect:dev"  # start server
      "qunit:develop"
  ]

  grunt.registerTask "sauce", [
      "connect:sauce",
      "saucelabs-qunit:ui_112",
    #   "saucelabs-qunit:ui_111",
    #   "saucelabs-qunit:ui_110",
  ]
  grunt.registerTask "sauce-optional", [
      "connect:sauce",
      "saucelabs-qunit:beta",
  ]
  grunt.registerTask "sauce-triage", ["connect:sauce", "saucelabs-qunit:triage"]

  # 2020-01-26 Saucelabs tests don't work.
  # Disable them in travis for now:
  grunt.registerTask "travis", ["test"]
  grunt.registerTask "travis-optional", []
  # if parseInt(process.env.TRAVIS_PULL_REQUEST, 10) > 0
  #     # saucelab keys do not work on forks
  #     # http://support.saucelabs.com/entries/25614798
  #     grunt.registerTask "travis", ["test"]
  #     grunt.registerTask "travis-optional", []
  # else
  #     grunt.registerTask "travis", ["test", "sauce"]
  #     grunt.registerTask "travis-optional", ["sauce-optional"]

  grunt.registerTask "default", ["test"]
  grunt.registerTask "ci", ["test"]  # Called by 'npm test'
  # Update package.json to latest versions (interactive)
  grunt.registerTask "dev-update", ["devUpdate"]

  grunt.registerTask "build", [
      "less:development"
      "format"
      # `test` also starts the connect:dev server
      "test"
      "jsdoc:build"
      "docco:docs"
      "clean:build"
      "copy:build"
      "cssmin:build"
      "concat:core_to_build"
      "concat:bundle_to_build"
      "uglify:src_to_build"
      "concat:amd_bundle_min"
      "concat:all_deps"
      "uglify:all_deps"
      "clean:post_build"
      "replace:production"
      "eslint:build"
      "copy:ui_deps"
      "qunit:build"
      ]

  grunt.registerTask "make_dist", [
      # `build` also starts the connect:dev server
      "build"
      "clean:dist"
      "copy:dist"
      "clean:build"
      "replace:release"
      # "eslint:dist"  # should rather use grunt-jsvalidate for minified output
      "qunit:dist"
      ]

  grunt.registerTask "upload", [
      "build"
      "exec:upload"
      ]

  grunt.registerTask "upload_force", [
      "build"
      "exec:upload_force"
      ]
