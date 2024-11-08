cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(Brain Implant Wizard)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/BrainImplantWizard")
set(EXTENSION_CATEGORY "Extension Development")
set(EXTENSION_CONTRIBUTORS "Arjun Khanna (UCSD Neurosurgery), ")
set(EXTENSION_DESCRIPTION "Modules to streamline brain electrode implantations.")
set(EXTENSION_ICONURL "https://www.example.com/Slicer/Extensions/BrainImplantWizard.png")
set(EXTENSION_SCREENSHOTURLS "https://www.example.com/Slicer/Extensions/BrainImplantWizard/Screenshots/1.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(ACPC)
add_subdirectory(ANTSRegistration)
add_subdirectory(Registration)
add_subdirectory(ANTSTemplateRegistration)
add_subdirectory(TemplateRegistration)
add_subdirectory(TrajectoryReview)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
