cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(CEMArtifacts)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/zapaishchykova/SegmentationReview")
set(EXTENSION_CATEGORY "Examples")
set(EXTENSION_CONTRIBUTORS "Donna Hooft (NKI, Watt group), Valentina Corbetta (NKI, Regina Beets Tan group)")
set(EXTENSION_DESCRIPTION "TSlicer extension for assessing artifacts on CEM images.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/DonnaHooft/CEMArtifacts/main/CEMArtifacts.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/DonnaHooft/CEMArtifacts-main/main/pics/screenshot.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(CEMArtifacts)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})


