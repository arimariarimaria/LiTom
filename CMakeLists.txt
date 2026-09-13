zephyr_library()

zephyr_library_sources_ifdef(CONFIG_LITOM_PREFER_USB_ENDPOINT_ON_READY src/prefer_usb_endpoint.c)
zephyr_library_sources_ifdef(CONFIG_LITOM_RECOVER_UNRESOLVED_BINDINGS src/keymap_compat.c)

# Keep the pinned dependency checkout untouched. Compile a corrected copy with
# timer/reconfiguration fixes required when using Studio's temporary layer UI.
if(CONFIG_ZMK_RUNTIME_INPUT_PROCESSOR)
  set_property(GLOBAL PROPERTY LITOM_MODULE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
  function(litom_patch_runtime_processor)
    get_property(litom_dir GLOBAL PROPERTY LITOM_MODULE_DIR)
    get_target_property(app_sources app SOURCES)
    set(runtime_sources ${app_sources})
    list(FILTER runtime_sources INCLUDE REGEX "/src/pointing/input_processor_runtime\\.c$")
    list(LENGTH runtime_sources runtime_count)
    if(NOT runtime_count EQUAL 1)
      message(FATAL_ERROR "LiTom expected one runtime input processor source")
    endif()
    list(GET runtime_sources 0 original)
    set(generated "${CMAKE_BINARY_DIR}/litom/input_processor_runtime.c")
    execute_process(
      COMMAND ${PYTHON_EXECUTABLE} "${litom_dir}/scripts/prepare_runtime_processor.py"
              "${original}" "${generated}"
      RESULT_VARIABLE result)
    if(NOT result EQUAL 0)
      message(FATAL_ERROR "LiTom runtime processor compatibility patch failed")
    endif()
    list(REMOVE_ITEM app_sources "${original}")
    set_property(TARGET app PROPERTY SOURCES "${app_sources}")
    target_sources(app PRIVATE "${generated}")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
      "${original}" "${litom_dir}/scripts/prepare_runtime_processor.py")
  endfunction()
  cmake_language(DEFER DIRECTORY "${CMAKE_SOURCE_DIR}" CALL litom_patch_runtime_processor)
endif()
