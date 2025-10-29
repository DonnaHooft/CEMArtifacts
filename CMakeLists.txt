cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(CEMArtifacts)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_NAME "CEMArtifacts")
set(EXTENSION_HOMEPAGE "https://github.com/DonnaHooft/CEMArtifacts-main")
set(EXTENSION_CATEGORY "Examples")
set(EXTENSION_CONTRIBUTORS "Donna Hooft;Valentina Corbetta")
set(EXTENSION_DESCRIPTION "Slicer extension for assessing artifacts on CEM images")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(CEMArtifacts)
add_subdirectory(Examples)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})


       