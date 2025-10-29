cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(CEMArtifacts)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/DonnaHooft/CEMArtifacts-main")
set(EXTENSION_CATEGORY "Segmentation")
set(EXTENSION_CONTRIBUTORS "Donna Hooft, Valentina Corbetta")
set(EXTENSION_DESCRIPTION "Slicer3D extension for assesing presence of artifacts on recombined Contrast Enhanced Mammography (CEM) images and for segmentation of Artifacts which are not locally bound.")
set(EXTENSION_ICONURL "https://raw.github.com/zapaishchykova/SegmentationReview/bd21693438a9bafed7e3a74313c0129860c9a74b/SlicerSegReview/Resources/Icons/SlicerSegReview.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/zapaishchykova/SegmentationReview/bd21693438a9bafed7e3a74313c0129860c9a74b/pics/screenshot.png")
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


       