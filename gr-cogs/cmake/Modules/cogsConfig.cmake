INCLUDE(FindPkgConfig)
PKG_CHECK_MODULES(PC_COGS cogs)

FIND_PATH(
    COGS_INCLUDE_DIRS
    NAMES cogs/api.h
    HINTS $ENV{COGS_DIR}/include
        ${PC_COGS_INCLUDEDIR}
    PATHS ${CMAKE_INSTALL_PREFIX}/include
          /usr/local/include
          /usr/include
)

FIND_LIBRARY(
    COGS_LIBRARIES
    NAMES gnuradio-cogs
    HINTS $ENV{COGS_DIR}/lib
        ${PC_COGS_LIBDIR}
    PATHS ${CMAKE_INSTALL_PREFIX}/lib
          ${CMAKE_INSTALL_PREFIX}/lib64
          /usr/local/lib
          /usr/local/lib64
          /usr/lib
          /usr/lib64
)

INCLUDE(FindPackageHandleStandardArgs)
FIND_PACKAGE_HANDLE_STANDARD_ARGS(COGS DEFAULT_MSG COGS_LIBRARIES COGS_INCLUDE_DIRS)
MARK_AS_ADVANCED(COGS_LIBRARIES COGS_INCLUDE_DIRS)

