# CopyPlugins.cmake — copy all plugin DLLs/SOs from the LMMS build tree
# into a flat plugins/ directory next to the exe.
# Called with: -DSRC_DIR=... -DDST_DIR=...

file(GLOB_RECURSE _plugin_files
    "${SRC_DIR}/*.dll"
    "${SRC_DIR}/*.so"
    "${SRC_DIR}/*.dylib"
)

foreach(_f ${_plugin_files})
    get_filename_component(_name "${_f}" NAME)
    # Skip autogen, moc, qrc build artifacts
    if(NOT _name MATCHES "^(moc_|qrc_|cmake)")
        file(COPY "${_f}" DESTINATION "${DST_DIR}")
        message(STATUS "  -> plugins/${_name}")
    endif()
endforeach()
